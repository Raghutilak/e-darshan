import base64
import hashlib
import itertools
import re
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import cv2
import numpy as np
from playwright.sync_api import sync_playwright

BASE_DIR = Path(__file__).resolve().parent
ANCHOR_DATE = date(2026, 9, 24)
MANGALA_ANCHOR_PAGE = 640
SRINGAR_ANCHOR_PAGE = 630
MIN_WIDTH = 500
MIN_HEIGHT = 300
MIN_BYTES = 100_000

# First finalized run only: verified previous-day references.
BOOTSTRAP = {
    "mangala": {641: {"reference_page": 640, "positions": [1, 5, 17]}},
    "sringar": {631: {"reference_page": 630, "positions": [1, 6, 21]}},
}

today = datetime.now(ZoneInfo("Asia/Kolkata")).date()
days_from_anchor = (today - ANCHOR_DATE).days
mangala_page = MANGALA_ANCHOR_PAGE + days_from_anchor
sringar_page = SRINGAR_ANCHOR_PAGE + days_from_anchor


def darshan_url(kind, page_number):
    if kind == "mangala":
        return f"https://www.iskconmumbai.com/mangala/mangal-darshan-{page_number}"
    if kind == "sringar":
        return f"https://www.iskconmumbai.com/sringar/sringar-darshan-{page_number}"
    raise ValueError(kind)


def data_url_to_bytes(data_url):
    match = re.match(r"data:image/[^;]+;base64,(.*)", data_url, re.DOTALL)
    if not match:
        return None
    try:
        return base64.b64decode(match.group(1))
    except Exception:
        return None


def bytes_to_image(data):
    return cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)


def extract_gallery(page):
    images = page.locator("img")
    gallery = []
    seen = set()
    for dom_index in range(images.count()):
        img = images.nth(dom_index)
        try:
            src = img.get_attribute("src")
            if not src or not src.startswith("data:image/"):
                continue
            width = img.evaluate("(el) => el.naturalWidth")
            height = img.evaluate("(el) => el.naturalHeight")
            if width < MIN_WIDTH or height < MIN_HEIGHT:
                continue
            data = data_url_to_bytes(src)
            if not data or len(data) < MIN_BYTES:
                continue
            digest = hashlib.sha256(data).hexdigest()
            if digest in seen:
                continue
            image = bytes_to_image(data)
            if image is None:
                continue
            seen.add(digest)
            gallery.append({
                "position": len(gallery) + 1,
                "dom": dom_index + 1,
                "width": width,
                "height": height,
                "bytes": len(data),
                "data": data,
                "image": image,
            })
        except Exception:
            continue
    return gallery


def load_gallery(page, kind, page_number):
    url = darshan_url(kind, page_number)
    print(f"\nOpening {kind} page {page_number}\n{url}")
    page.goto(url, wait_until="domcontentloaded", timeout=120000)
    page.wait_for_timeout(6000)
    for _ in range(12):
        page.mouse.wheel(0, 1000)
        page.wait_for_timeout(700)
    page.wait_for_timeout(3000)
    gallery = extract_gallery(page)
    print(f"Real gallery photos: {len(gallery)}")
    if len(gallery) < 3:
        raise RuntimeError(f"{kind}: fewer than 3 real gallery photos found")
    return gallery


def load_bootstrap_references(page, kind, reference_page, positions):
    gallery = load_gallery(page, kind, reference_page)
    refs = []
    print(f"Bootstrap {kind} references from page {reference_page}: {positions}")
    for number, position in enumerate(positions, 1):
        if position > len(gallery):
            raise RuntimeError(f"{kind}: reference position {position} not found on page {reference_page}")
        item = gallery[position - 1]
        refs.append({"number": number, "image": item["image"]})
        print(f"Reference #{number}: page {reference_page} gallery #{position} {item['width']}x{item['height']}")
    return refs


def load_committed_references(kind):
    refs = []
    for number in range(1, 4):
        path = BASE_DIR / f"{kind}-{number}.jpg"
        if not path.exists():
            raise RuntimeError(f"Missing previous-day reference file: {path}")
        image = bytes_to_image(path.read_bytes())
        if image is None:
            raise RuntimeError(f"Cannot decode previous-day reference: {path}")
        refs.append({"number": number, "image": image})
    print(f"Using committed previous-day {kind} photos as references")
    return refs


def get_references(page, kind, target_page):
    bootstrap = BOOTSTRAP.get(kind, {}).get(target_page)
    if bootstrap:
        return load_bootstrap_references(page, kind, bootstrap["reference_page"], bootstrap["positions"])
    return load_committed_references(kind)


def normalize_image(image, size=320):
    h, w = image.shape[:2]
    scale = min(size / w, size / h)
    nw = max(1, int(w * scale))
    nh = max(1, int(h * scale))
    resized = cv2.resize(image, (nw, nh), interpolation=cv2.INTER_AREA)
    canvas = np.zeros((size, size, 3), dtype=np.uint8)
    x = (size - nw) // 2
    y = (size - nh) // 2
    canvas[y:y + nh, x:x + nw] = resized
    return canvas


def sift_score(a, b):
    a = cv2.cvtColor(a, cv2.COLOR_BGR2GRAY)
    b = cv2.cvtColor(b, cv2.COLOR_BGR2GRAY)
    sift = cv2.SIFT_create(nfeatures=2500, contrastThreshold=0.02, edgeThreshold=10, sigma=1.6)
    kpa, desa = sift.detectAndCompute(a, None)
    kpb, desb = sift.detectAndCompute(b, None)
    if desa is None or desb is None or len(desa) < 2 or len(desb) < 2:
        return 0.0
    matches = cv2.BFMatcher(cv2.NORM_L2).knnMatch(desa, desb, k=2)
    good = [m for pair in matches if len(pair) == 2 for m, n in [pair] if m.distance < 0.72 * n.distance]
    if not good:
        return 0.0
    inliers = 0
    if len(good) >= 4:
        src = np.float32([kpa[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
        dst = np.float32([kpb[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
        try:
            _, mask = cv2.findHomography(src, dst, cv2.RANSAC, 5.0)
            if mask is not None:
                inliers = int(mask.ravel().sum())
        except Exception:
            pass
    return 0.8 * min(inliers / 80.0, 1.0) + 0.2 * min(len(good) / 150.0, 1.0)


def orb_score(a, b):
    a = cv2.cvtColor(a, cv2.COLOR_BGR2GRAY)
    b = cv2.cvtColor(b, cv2.COLOR_BGR2GRAY)
    orb = cv2.ORB_create(nfeatures=3000)
    kpa, desa = orb.detectAndCompute(a, None)
    kpb, desb = orb.detectAndCompute(b, None)
    if desa is None or desb is None or len(desa) < 2 or len(desb) < 2:
        return 0.0
    matches = cv2.BFMatcher(cv2.NORM_HAMMING).knnMatch(desa, desb, k=2)
    good = [m for pair in matches if len(pair) == 2 for m, n in [pair] if m.distance < 0.75 * n.distance]
    if not good:
        return 0.0
    inliers = 0
    if len(good) >= 4:
        src = np.float32([kpa[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
        dst = np.float32([kpb[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
        try:
            _, mask = cv2.findHomography(src, dst, cv2.RANSAC, 5.0)
            if mask is not None:
                inliers = int(mask.ravel().sum())
        except Exception:
            pass
    return 0.8 * min(inliers / 60.0, 1.0) + 0.2 * min(len(good) / 120.0, 1.0)


def phash_score(a, b):
    def h(image):
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        gray = cv2.resize(gray, (32, 32), interpolation=cv2.INTER_AREA)
        dct = cv2.dct(np.float32(gray))[:8, :8]
        return (dct > np.median(dct)).flatten()
    ha, hb = h(a), h(b)
    return 1.0 - (np.count_nonzero(ha != hb) / len(ha))


def structure_score(a, b):
    a = cv2.cvtColor(normalize_image(a), cv2.COLOR_BGR2GRAY).astype(np.float32)
    b = cv2.cvtColor(normalize_image(b), cv2.COLOR_BGR2GRAY).astype(np.float32)
    ma = cv2.GaussianBlur(a, (11, 11), 1.5)
    mb = cv2.GaussianBlur(b, (11, 11), 1.5)
    va = cv2.GaussianBlur(a * a, (11, 11), 1.5) - ma * ma
    vb = cv2.GaussianBlur(b * b, (11, 11), 1.5) - mb * mb
    cov = cv2.GaussianBlur(a * b, (11, 11), 1.5) - ma * mb
    c1, c2 = 6.5025, 58.5225
    score = ((2 * ma * mb + c1) * (2 * cov + c2)) / (((ma * ma + mb * mb + c1) * (va + vb + c2)) + 1e-8)
    return float(np.clip(np.mean(score), 0.0, 1.0))


def edge_score(a, b):
    a = cv2.Canny(cv2.cvtColor(normalize_image(a), cv2.COLOR_BGR2GRAY), 60, 140).astype(np.float32) / 255.0
    b = cv2.Canny(cv2.cvtColor(normalize_image(b), cv2.COLOR_BGR2GRAY), 60, 140).astype(np.float32) / 255.0
    a, b = a.flatten(), b.flatten()
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.clip(np.dot(a, b) / (na * nb), 0.0, 1.0))


def hsv_score(a, b):
    a = cv2.cvtColor(normalize_image(a), cv2.COLOR_BGR2HSV)
    b = cv2.cvtColor(normalize_image(b), cv2.COLOR_BGR2HSV)
    ha = cv2.calcHist([a], [0, 1], None, [32, 32], [0, 180, 0, 256])
    hb = cv2.calcHist([b], [0, 1], None, [32, 32], [0, 180, 0, 256])
    cv2.normalize(ha, ha, 0, 1, cv2.NORM_MINMAX)
    cv2.normalize(hb, hb, 0, 1, cv2.NORM_MINMAX)
    correlation = cv2.compareHist(ha, hb, cv2.HISTCMP_CORREL)
    return float(np.clip((correlation + 1.0) / 2.0, 0.0, 1.0))


def color_score(a, b):
    a = normalize_image(a).astype(np.float32)
    b = normalize_image(b).astype(np.float32)
    fa = np.concatenate([np.mean(a, axis=(0, 1)), np.std(a, axis=(0, 1))])
    fb = np.concatenate([np.mean(b, axis=(0, 1)), np.std(b, axis=(0, 1))])
    return float(np.exp(-np.linalg.norm(fa - fb) / 80.0))


def similarity(reference, candidate):
    scores = {
        "sift": sift_score(reference, candidate),
        "orb": orb_score(reference, candidate),
        "phash": phash_score(reference, candidate),
        "structure": structure_score(reference, candidate),
        "edges": edge_score(reference, candidate),
        "hsv": hsv_score(reference, candidate),
        "color": color_score(reference, candidate),
    }
    return sum(scores.values()) / len(scores), scores


def select_unique_matches(references, candidates):
    matrix = np.zeros((len(references), len(candidates)), dtype=np.float32)
    for ri, reference in enumerate(references):
        print(f"Comparing reference #{reference['number']}...")
        for ci, candidate in enumerate(candidates):
            matrix[ri, ci], _ = similarity(reference["image"], candidate["image"])

    best_total = -1.0
    best_assignment = None
    for assignment in itertools.permutations(range(len(candidates)), len(references)):
        total = sum(matrix[ri, ci] for ri, ci in enumerate(assignment))
        if total > best_total:
            best_total = total
            best_assignment = assignment

    selected = []
    for ri, ci in enumerate(best_assignment):
        final_score, scores = similarity(references[ri]["image"], candidates[ci]["image"])
        selected.append({
            "reference_number": references[ri]["number"],
            "candidate": candidates[ci],
            "final_score": final_score,
            "scores": scores,
        })
    return selected, best_total


def save_selected(kind, selected):
    for number, result in enumerate(selected, 1):
        path = BASE_DIR / f"{kind}-{number}.jpg"
        path.write_bytes(result["candidate"]["data"])
        print(f"Saved {path.name} ({len(result['candidate']['data']):,} bytes)")


def process_kind(page, kind, target_page):
    references = get_references(page, kind, target_page)
    gallery = load_gallery(page, kind, target_page)
    candidates = [item for item in gallery if item["width"] > item["height"]]

    print(f"{kind}: landscape candidates for page {target_page}: {len(candidates)}")
    for item in candidates:
        print(f"  #{item['position']}: {item['width']}x{item['height']}")

    if len(candidates) < 3:
        raise RuntimeError(f"{kind}: fewer than 3 landscape candidates on page {target_page}")

    selected, total_score = select_unique_matches(references, candidates)

    print(f"\n{kind.upper()} FINAL SELECTION")
    used = set()
    for result in selected:
        pos = result["candidate"]["position"]
        if pos in used:
            raise RuntimeError(f"{kind}: duplicate candidate selected: #{pos}")
        used.add(pos)
        print(f"Reference #{result['reference_number']} -> page {target_page} gallery #{pos} score={result['final_score']:.4f}")
        s = result["scores"]
        print("  " + " ".join(f"{k}={v:.4f}" for k, v in s.items()))

    save_selected(kind, selected)
    print(f"{kind}: total assignment score={total_score:.4f}")


def main():
    print("========================================")
    print("ISKCON Juhu Daily Darshan Updater")
    print("Rolling previous-day visual matcher")
    print("========================================")
    print(f"India date: {today}")
    print(f"Days from anchor: {days_from_anchor}")
    print(f"Mangala page: {mangala_page}")
    print(f"Sringar page: {sringar_page}")

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1200})
        try:
            process_kind(page, "mangala", mangala_page)
            process_kind(page, "sringar", sringar_page)
        finally:
            browser.close()

    print("\n========================================")
    print("Update completed successfully.")
    print("========================================")


if __name__ == "__main__":
    main()
