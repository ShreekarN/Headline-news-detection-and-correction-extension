
import io, base64, logging
from urllib.parse import urljoin
from PIL import Image, ImageChops, ImageStat, ImageFile
import requests

ImageFile.LOAD_TRUNCATED_IMAGES = True
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

SUSPICIOUS_TOKENS = ['edited','photoshop','photoshopped','ai','generated','deepfake','manipulated','remix']

def _is_data_uri(u):
    return (u or '').startswith('data:')

def _should_skip_image_url(url):
    lower = (url or '').lower()
    if lower.endswith('.svg') or '.svg?' in lower:
        return True
    if any(tok in lower for tok in ('/logo', 'logo.', 'footer', '/icon', 'favicon', 'sprite', 'avatar')):
        return True
    return False

def _load_image_from_data_uri(data_uri):
    try:
        header, b64 = data_uri.split(',', 1)
        data = base64.b64decode(b64)
        return Image.open(io.BytesIO(data)).convert('RGB')
    except Exception as e:
        raise RuntimeError(f"data-uri decode error: {e}")

def _resolve_image_url(url, page_url=None):
    u = (url or '').strip()
    if not u or u.startswith('data:'):
        return u
    if u.startswith(('http://', 'https://')):
        return u
    if page_url:
        return urljoin(page_url, u)
    return u

def _fetch_image_from_url(url, timeout=6):
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (compatible; news-checker-bot/1.0)'}
        r = requests.get(url, timeout=timeout, headers=headers)
        if r.status_code != 200:
            raise RuntimeError(f'HTTP {r.status_code}')
        return Image.open(io.BytesIO(r.content)).convert('RGB')
    except Exception as e:
        raise RuntimeError(f'fetch error: {e}')

def _ela_score(img, resave_quality=90):
    try:
        with io.BytesIO() as orig_buf:
            img.save(orig_buf, format='JPEG', quality=95)
            orig_bytes = orig_buf.getvalue()

        with io.BytesIO() as recompressed_buf:
            img.save(recompressed_buf, format='JPEG', quality=resave_quality)
            recompressed_bytes = recompressed_buf.getvalue()

        orig = Image.open(io.BytesIO(orig_bytes)).convert('RGB')
        recompressed = Image.open(io.BytesIO(recompressed_bytes)).convert('RGB')
        diff = ImageChops.difference(orig, recompressed)
        stat = ImageStat.Stat(diff)
        mean_diff = sum(stat.mean) / len(stat.mean)
        score = (mean_diff / 255.0) * 100.0
        return float(score)
    except Exception as e:
        logger.info(f'ELA failed: {e}')
        return 0.0

def _exif_flags(img):
    flags = []
    try:
        exif = img.getexif()
        if exif:
            for tag, value in exif.items():
                sval = str(value).lower()
                if 'photoshop' in sval or 'adobe' in sval or 'gimp' in sval:
                    flags.append(f'exif indicates editor:{sval[:40]}')
    except Exception:
        pass
    return flags

def analyze_images(image_urls, try_fetch=False, page_url=None):
    reports = []
    for url in image_urls:
        url = _resolve_image_url(url, page_url)
        if _should_skip_image_url(url):
            reports.append({'image': url, 'status': 'skipped', 'reasons': ['logo or non-photo asset']})
            continue

        reasons = []
        status = 'likely_authentic'
        lower = (url or '').lower()

        for t in SUSPICIOUS_TOKENS:
            if t in lower:
                reasons.append(f"filename contains '{t}'")

        if 'filter=' in lower or 'manipulate=' in lower or ('w=' in lower and 'h=' in lower and 'blur' in lower):
            reasons.append('URL includes image transformation parameters')

        img = None
        if _is_data_uri(lower):
            try:
                img = _load_image_from_data_uri(url)
            except Exception as e:
                reasons.append(str(e))
        elif try_fetch:
            try:
                img = _fetch_image_from_url(url)
            except Exception as e:
                reasons.append(str(e))

        if img is not None:
            ela = _ela_score(img)
            if ela > 5.0:
                reasons.append(f'ELA score={ela:.2f}')
            exflags = _exif_flags(img)
            reasons.extend(exflags)

        if reasons:
            status = 'suspicious'
        reports.append({'image': url, 'status': status, 'reasons': reasons})
    return reports
