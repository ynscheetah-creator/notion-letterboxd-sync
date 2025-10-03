"""
boxd.it kısaltmalarını gerçek başlığa yaklaştıran küçük yardımcı.
Gerçek Letterboxd sayfasını scrap’lemiyoruz; sadece slug -> title tahmini.
"""
import re
import requests

def from_boxd(url: str) -> dict:
    if not url:
        return {}
    try:
        # redirect’i takip et
        r = requests.get(url, timeout=20, allow_redirects=True)
        final = r.url
    except Exception:
        final = url

    # ör: https://letterboxd.com/film/2001-a-space-odyssey/
    m = re.search(r"/film/([^/]+)/?", final)
    title = None
    year = None
    if m:
        slug = m.group(1)
        # slug’ı başlığa çevir
        title = re.sub(r"[-_]+", " ", slug).strip().title()
        # “-2018” gibi yıl içeren slug yakalanırsa
        ym = re.search(r"(\d{4})$", title)
        if ym:
            year = int(ym.group(1))
    return {"title": title, "year": year}
