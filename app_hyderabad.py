import json
import re
import csv
import time
import os
import threading
import webbrowser
from io import StringIO
from urllib.parse import urlparse, quote
from concurrent.futures import ThreadPoolExecutor, as_completed
from flask import Flask, render_template_string, request, jsonify, make_response
import requests
from bs4 import BeautifulSoup

try:
    from apify_client import ApifyClient
    APIFY_AVAILABLE = True
except ImportError:
    APIFY_AVAILABLE = False
    print("[WARN] apify-client not installed. Run: pip install apify-client")

app = Flask(__name__)
extracted_businesses = []

# ============================================================
#  CONFIG
# ============================================================
HYDERABAD_LAT = 17.3850
HYDERABAD_LNG = 78.4867
SEARCH_RADIUS = 5000
HISTORY_FILE = "extracted_history.json"

HYDERABAD_AREAS = {
    "Central":            (17.3850, 78.4867),
    "Secunderabad":       (17.4000, 78.4750),
    "Kompally":           (17.4400, 78.4980),
    "Mehdipatnam":        (17.3600, 78.4740),
    "HITEC City":         (17.4435, 78.3772),
    "Gachibowli":        (17.4400, 78.3500),
    "Financial District": (17.4239, 78.3420),
    "Kondapur":           (17.4600, 78.3600),
    "Uppal":              (17.3950, 78.5500),
    "LB Nagar":           (17.3700, 78.5300),
    "Hayathnagar":        (17.3500, 78.5700),
    "Nacharam":           (17.4200, 78.5400),
    "Alwal":              (17.4800, 78.4900),
    "Bollaram":           (17.5100, 78.4700),
    "Bowenpally":         (17.4600, 78.4400),
    "Miyapur":            (17.4900, 78.3900),
    "Shamshabad":         (17.3200, 78.5000),
    "Attapur":            (17.3400, 78.4500),
    "Rajendranagar":      (17.3100, 78.4700),
    "Tolichowki":         (17.3600, 78.4200),
    "Patancheru":         (17.4100, 78.3200),
    "Narsingi":           (17.3900, 78.3600),
    "Manikonda":          (17.3700, 78.3900),
    "Begumpet":           (17.4300, 78.4500),
    "Banjara Hills":      (17.4150, 78.4350),
    "Ameerpet":           (17.4100, 78.4550),
    "Tarnaka":            (17.4050, 78.5000),
    "Dilsukhnagar":       (17.3800, 78.5100),
    "Kukatpally":         (17.4700, 78.4200),
    "Madhapur":           (17.4480, 78.3910),
}

CATEGORIES = {
    "it_companies":    {"keyword": "IT companies",           "type": "establishment"},
    "software":        {"keyword": "software company",       "type": "establishment"},
    "startups":        {"keyword": "startup",                "type": "establishment"},
    "restaurants":     {"keyword": "restaurant",             "type": "restaurant"},
    "hospitals":       {"keyword": "hospital",               "type": "hospital"},
    "hotels":          {"keyword": "hotel",                  "type": "lodging"},
    "real_estate":     {"keyword": "real estate agency",     "type": "real_estate_agency"},
    "gyms":            {"keyword": "gym fitness",            "type": "gym"},
    "education":       {"keyword": "coaching institute",     "type": "establishment"},
    "retail_shops":    {"keyword": "retail shop",            "type": "store"},
    "manufacturers":   {"keyword": "manufacturer factory",   "type": "establishment"},
    "pharma":          {"keyword": "pharmaceutical company", "type": "establishment"},
    "marketing":       {"keyword": "marketing agency",       "type": "establishment"},
    "logistics":       {"keyword": "logistics courier",      "type": "establishment"},
    "automobile":      {"keyword": "car dealer showroom",    "type": "car_dealer"},
}

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", re.IGNORECASE)
JUNK_EMAILS = {"sentry@","wixpress","example.com","domain.com","email@","username@","test@","noreply@","no-reply@",".png",".jpg",".gif",".svg",".webp","google.com","gstatic","w3.org","schema.org","facebook.com","twitter.com","instagram.com","youtube.com"}
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}

def is_junk_email(email):
    return any(j in email.lower() for j in JUNK_EMAILS)


# ============================================================
#  PHONE NUMBER UTILITIES
# ============================================================
def clean_phone(phone):
    """Clean and standardize Indian phone number."""
    if not phone or phone == "N/A":
        return "N/A", "unknown", ""

    # Remove all formatting
    cleaned = re.sub(r"[\s\-\(\)\.\+]", "", phone)

    # Remove leading 0 or 91
    if cleaned.startswith("91") and len(cleaned) > 10:
        cleaned = cleaned[2:]
    if cleaned.startswith("0") and len(cleaned) > 10:
        cleaned = cleaned[1:]

    # Indian mobile: 10 digits starting with 6-9
    if re.match(r"^[6-9]\d{9}$", cleaned):
        formatted = f"+91{cleaned}"
        return formatted, "mobile", cleaned

    # Indian landline: typically 10-11 digits starting with 0 + area code
    if re.match(r"^[0-9]\d{6,10}$", cleaned) and len(cleaned) >= 7:
        return phone, "landline", ""

    return phone, "unknown", ""


def generate_whatsapp_link(mobile_number, message=""):
    """Generate WhatsApp click-to-chat link."""
    if not mobile_number:
        return ""
    # Remove + from number for wa.me
    num = mobile_number.replace("+", "")
    if message:
        return f"https://wa.me/{num}?text={quote(message)}"
    return f"https://wa.me/{num}"


# ============================================================
#  HISTORY
# ============================================================
def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {"extracted_ids": [], "run_count": 0, "total_extracted": 0}

def save_history(history):
    try:
        with open(HISTORY_FILE, "w") as f:
            json.dump(history, f)
    except Exception:
        pass


# ============================================================
#  APIFY
# ============================================================
def extract_with_apify(apify_token, search_queries, areas):
    if not APIFY_AVAILABLE or not apify_token:
        return []

    client = ApifyClient(apify_token)
    all_businesses = []

    search_strings = []
    for query in search_queries:
        for area in areas:
            search_strings.append(f"{query} in {area}, Hyderabad, India")

    print(f"[APIFY] {len(search_strings)} search queries...")

    try:
        run_input = {
            "searchStringsArray": search_strings,
            "maxCrawledPlacesPerSearch": 20,
            "language": "en",
            "scrapeEmails": True,
            "scrapeContacts": True,
        }

        run = client.actor("compass/crawler-google-places").call(run_input=run_input, timeout_secs=300)

        if run and run.get("defaultDatasetId"):
            for item in client.dataset(run["defaultDatasetId"]).iterate_items():
                phone_raw = item.get("phone") or item.get("phoneUnformatted") or "N/A"
                phone_clean, phone_type, mobile_digits = clean_phone(phone_raw)

                emails = item.get("emails", [])
                email_str = ", ".join(emails) if emails else "N/A"

                wa_link = ""
                if phone_type == "mobile" and mobile_digits:
                    wa_link = generate_whatsapp_link(phone_clean)

                biz = {
                    "company": item.get("title") or item.get("name") or "N/A",
                    "address": item.get("address") or "N/A",
                    "phone": phone_clean,
                    "phone_type": phone_type,
                    "email": email_str,
                    "email_type": "verified" if emails else "N/A",
                    "website": item.get("website") or "N/A",
                    "rating": item.get("totalScore") or "N/A",
                    "reviews": item.get("reviewsCount") or 0,
                    "status": "OPERATIONAL" if not item.get("permanentlyClosed") else "CLOSED",
                    "area": item.get("neighborhood") or item.get("city") or "N/A",
                    "maps_link": item.get("url") or "",
                    "whatsapp_link": wa_link,
                    "social_facebook": item.get("facebookUrl") or "N/A",
                    "social_instagram": item.get("instagramUrl") or "N/A",
                    "social_linkedin": item.get("linkedinUrl") or "N/A",
                    "source": "Apify",
                }
                all_businesses.append(biz)

            print(f"[APIFY] Got {len(all_businesses)} businesses")

    except Exception as e:
        print(f"[APIFY] Error: {e}")

    return all_businesses


# ============================================================
#  JUSTDIAL via Apify
# ============================================================
def extract_from_justdial(apify_token, search_queries, areas):
    """Use Apify JustDial Scraper to get businesses with phone numbers."""
    if not APIFY_AVAILABLE or not apify_token:
        return []

    client = ApifyClient(apify_token)
    all_businesses = []

    # Build JustDial search URLs
    search_urls = []
    for area in areas:
        for query in search_queries:
            # JustDial URL format: justdial.com/Hyderabad/IT-Companies-in-HITEC-City
            area_slug = area.replace(" ", "-")
            query_slug = query.replace(" ", "-")
            search_urls.append(f"https://www.justdial.com/Hyderabad/{query_slug}-in-{area_slug}")

    print(f"[JUSTDIAL] Searching {len(search_urls)} URLs...")

    try:
        # Try the JustDial Business Leads Scraper
        run_input = {
            "searchUrls": search_urls[:20],  # Limit to avoid high usage
            "maxItems": 50,
        }

        # Try multiple actor IDs (different JustDial scrapers on Apify)
        actor_ids = [
            "scrapeai/justdial-business-leads-scraper",
            "krawlify/justdial-extractor",
            "thirdwatch/justdial-business-scraper",
        ]

        for actor_id in actor_ids:
            try:
                print(f"[JUSTDIAL] Trying actor: {actor_id}")
                run = client.actor(actor_id).call(run_input=run_input, timeout_secs=180)

                if run and run.get("defaultDatasetId"):
                    count = 0
                    for item in client.dataset(run["defaultDatasetId"]).iterate_items():
                        phone_raw = (
                            item.get("phone")
                            or item.get("phoneNumber")
                            or item.get("contact")
                            or item.get("mobile")
                            or "N/A"
                        )
                        phone_clean, phone_type, mobile_digits = clean_phone(phone_raw)

                        email = item.get("email") or item.get("emailId") or "N/A"
                        website = item.get("website") or item.get("websiteUrl") or "N/A"

                        wa_link = ""
                        if phone_type == "mobile" and mobile_digits:
                            wa_link = generate_whatsapp_link(phone_clean)

                        biz = {
                            "company": item.get("name") or item.get("businessName") or item.get("title") or "N/A",
                            "address": item.get("address") or item.get("location") or "N/A",
                            "phone": phone_clean,
                            "phone_type": phone_type,
                            "email": email,
                            "email_type": "verified" if email != "N/A" else "N/A",
                            "website": website,
                            "rating": item.get("rating") or item.get("ratings") or "N/A",
                            "reviews": item.get("reviewCount") or item.get("reviews") or 0,
                            "status": "OPERATIONAL",
                            "area": item.get("area") or item.get("locality") or "N/A",
                            "maps_link": item.get("justdialUrl") or item.get("url") or "",
                            "whatsapp_link": wa_link,
                            "social_facebook": "N/A",
                            "social_instagram": "N/A",
                            "social_linkedin": "N/A",
                            "source": "JustDial",
                        }
                        all_businesses.append(biz)
                        count += 1

                    if count > 0:
                        print(f"[JUSTDIAL] Got {count} businesses from {actor_id}")
                        break  # Success, no need to try other actors

            except Exception as e:
                print(f"[JUSTDIAL] {actor_id} failed: {e}")
                continue

    except Exception as e:
        print(f"[JUSTDIAL] Error: {e}")

    return all_businesses


# ============================================================
#  GOOGLE PLACES
# ============================================================
def google_nearby_search(api_key, lat, lng, keyword, place_type, max_pages=2):
    url = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
    params = {"location": f"{lat},{lng}", "radius": SEARCH_RADIUS, "keyword": keyword, "type": place_type, "key": api_key}
    results = []
    for _ in range(max_pages):
        resp = requests.get(url, params=params, timeout=15).json()
        if resp.get("status") not in ("OK", "ZERO_RESULTS"):
            break
        results.extend(resp.get("results", []))
        token = resp.get("next_page_token")
        if not token:
            break
        time.sleep(2)
        params = {"pagetoken": token, "key": api_key}
    return results

def google_place_details(api_key, place_id):
    url = "https://maps.googleapis.com/maps/api/place/details/json"
    params = {"place_id": place_id, "fields": "formatted_phone_number,international_phone_number,website,formatted_address,url,business_status", "key": api_key}
    try:
        resp = requests.get(url, params=params, timeout=10).json()
        if resp.get("status") == "OK":
            return resp.get("result", {})
    except Exception:
        pass
    return {}


# ============================================================
#  WEBSITE SCRAPING — Emails + Extra phones
# ============================================================
def scrape_website_data(website_url, timeout=8):
    """Scrape emails AND phone numbers from website."""
    if not website_url:
        return [], []
    try:
        emails = set()
        phones = set()
        phone_re = re.compile(r"(?:\+91[\s\-]?)?[6-9]\d{4}[\s\-]?\d{5}")

        pages_to_check = [website_url]
        try:
            resp = requests.get(website_url, headers=HEADERS, timeout=timeout, allow_redirects=True)
            resp.raise_for_status()
            text = resp.text
            emails |= {e for e in EMAIL_RE.findall(text) if not is_junk_email(e)}
            phones |= set(phone_re.findall(text))

            soup = BeautifulSoup(text, "html.parser")
            for a in soup.find_all("a", href=True):
                href = a["href"].lower()
                if any(kw in href for kw in ["contact", "about", "reach", "support", "enquiry"]):
                    if href.startswith("/"):
                        pages_to_check.append(website_url.rstrip("/") + href)
        except Exception:
            pass

        for suffix in ["/contact", "/contact-us", "/about", "/about-us"]:
            pages_to_check.append(website_url.rstrip("/") + suffix)

        for link in list(set(pages_to_check))[1:8]:
            try:
                sub = requests.get(link, headers=HEADERS, timeout=6, allow_redirects=True)
                if sub.status_code == 200:
                    emails |= {e for e in EMAIL_RE.findall(sub.text) if not is_junk_email(e)}
                    phones |= set(phone_re.findall(sub.text))
            except Exception:
                continue

        return list(emails)[:5], list(phones)[:3]
    except Exception:
        return [], []


def generate_common_emails(website):
    if not website or website == "N/A":
        return []
    try:
        domain = urlparse(website).netloc
        if domain.startswith("www."):
            domain = domain[4:]
        if not domain or any(sd in domain for sd in ["google","facebook","instagram","youtube","justdial","indiamart"]):
            return []
        return [f"info@{domain}"]
    except Exception:
        return []


def enrich_google_place(api_key, place, area_name):
    details = google_place_details(api_key, place.get("place_id", "")) if place.get("place_id") else {}

    phone_raw = details.get("formatted_phone_number") or details.get("international_phone_number") or "N/A"
    website = details.get("website", "")
    company_name = place.get("name", "N/A")

    # Scrape website for emails AND extra phone numbers
    scraped_emails, scraped_phones = scrape_website_data(website)

    # If Google didn't give a mobile number, try scraped phones
    phone_clean, phone_type, mobile_digits = clean_phone(phone_raw)
    if phone_type != "mobile" and scraped_phones:
        for sp in scraped_phones:
            sp_clean, sp_type, sp_digits = clean_phone(sp)
            if sp_type == "mobile":
                phone_clean = sp_clean
                phone_type = sp_type
                mobile_digits = sp_digits
                break

    # Emails
    email_type = "verified" if scraped_emails else "N/A"
    if not scraped_emails:
        guessed = generate_common_emails(website)
        if guessed:
            scraped_emails = guessed
            email_type = "guessed"

    # WhatsApp link
    wa_link = ""
    if phone_type == "mobile" and mobile_digits:
        wa_link = generate_whatsapp_link(phone_clean)

    return {
        "company": company_name,
        "address": details.get("formatted_address") or place.get("vicinity", "N/A"),
        "phone": phone_clean,
        "phone_type": phone_type,
        "email": ", ".join(scraped_emails) if scraped_emails else "N/A",
        "email_type": email_type,
        "website": website or "N/A",
        "rating": place.get("rating", "N/A"),
        "reviews": place.get("user_ratings_total", 0),
        "status": details.get("business_status", "N/A"),
        "area": area_name,
        "maps_link": details.get("url", ""),
        "whatsapp_link": wa_link,
        "social_facebook": "N/A",
        "social_instagram": "N/A",
        "social_linkedin": "N/A",
        "source": "Google Places",
    }


# ============================================================
#  HTML
# ============================================================
CATS_JSON = json.dumps({k: {"keyword": v["keyword"]} for k, v in CATEGORIES.items()})
AREAS_JSON = json.dumps(list(HYDERABAD_AREAS.keys()))

HTML = r"""
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>AI Business Extractor + WhatsApp</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Segoe UI',sans-serif;background:linear-gradient(135deg,#0f0c29,#302b63,#24243e);min-height:100vh;color:#e0e0e0}
.header{text-align:center;padding:30px 20px 12px}
.header h1{font-size:30px;background:linear-gradient(135deg,#25D366,#667eea,#764ba2);-webkit-background-clip:text;-webkit-text-fill-color:transparent;margin-bottom:6px}
.header p{color:#aaa;font-size:13px}
.tag{display:inline-block;padding:3px 10px;border-radius:15px;font-size:10px;font-weight:700;margin:4px 2px}
.tag-green{background:rgba(37,211,102,.2);color:#25D366}
.tag-blue{background:rgba(102,126,234,.2);color:#667eea}
.tag-purple{background:rgba(118,75,162,.2);color:#c9b1ff}
.main{max-width:1400px;margin:0 auto;padding:12px}
.card{background:rgba(255,255,255,0.06);border:1px solid rgba(255,255,255,0.1);border-radius:14px;padding:22px;margin-bottom:16px}
.card h2{font-size:17px;margin-bottom:12px;color:#c9b1ff}
.form-row{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:12px}
.form-group{flex:1;min-width:170px}
.form-group label{display:block;font-size:11px;font-weight:600;color:#bbb;margin-bottom:4px}
.form-group input,.form-group select,.form-group textarea{width:100%;padding:9px;border:1px solid rgba(255,255,255,0.15);border-radius:8px;background:rgba(255,255,255,0.07);color:#fff;font-size:12px;outline:none}
.form-group textarea{height:60px;resize:vertical;font-family:inherit}
.form-group input:focus,.form-group select:focus,.form-group textarea:focus{border-color:#25D366}
select option{background:#302b63;color:#fff}
.btn{padding:10px 22px;border:none;border-radius:8px;font-weight:700;font-size:13px;cursor:pointer;transition:.3s}
.btn-primary{background:linear-gradient(135deg,#667eea,#764ba2);color:#fff}
.btn-primary:hover{transform:translateY(-2px);box-shadow:0 6px 18px rgba(102,126,234,.4)}
.btn-primary:disabled{opacity:.5;cursor:not-allowed;transform:none}
.btn-success{background:linear-gradient(135deg,#11998e,#38ef7d);color:#000}
.btn-whatsapp{background:#25D366;color:#fff}
.btn-whatsapp:hover{background:#128C7E;transform:translateY(-1px)}
.btn-danger{background:#e74c3c;color:#fff}
.btn-row{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-top:8px}
.stats{display:flex;gap:8px;flex-wrap:wrap;margin-top:14px}
.stat-box{flex:1;min-width:85px;background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.08);border-radius:10px;padding:10px;text-align:center}
.stat-box .num{font-size:20px;font-weight:800;background:linear-gradient(135deg,#667eea,#f093fb);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.stat-wa .num{background:linear-gradient(135deg,#25D366,#128C7E);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.stat-box .lbl{font-size:9px;color:#999;margin-top:2px}
.msg{margin-top:12px;padding:10px;border-radius:8px;font-size:12px;display:none}
.msg.show{display:block}
.msg.error{background:rgba(220,53,69,.15);color:#ff6b6b;border:1px solid rgba(220,53,69,.25)}
.msg.success{background:rgba(56,239,125,.1);color:#38ef7d;border:1px solid rgba(56,239,125,.2)}
.msg.loading{background:rgba(102,126,234,.1);color:#a5b4fc;border:1px solid rgba(102,126,234,.2)}
.table-wrap{overflow-x:auto;margin-top:12px;border-radius:10px;border:1px solid rgba(255,255,255,.08)}
table{width:100%;border-collapse:collapse;font-size:11px}
th{background:rgba(102,126,234,.25);color:#c9b1ff;padding:8px 5px;text-align:left;white-space:nowrap;font-weight:700;position:sticky;top:0}
td{padding:6px 5px;border-bottom:1px solid rgba(255,255,255,.06);max-width:150px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
tr:hover td{background:rgba(255,255,255,.04)}
a{color:#667eea;text-decoration:none}
.checkbox-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:5px;margin-top:5px}
.checkbox-grid label{display:flex;align-items:center;gap:4px;font-size:11px;color:#ccc;cursor:pointer;padding:4px 7px;border-radius:6px;background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.08)}
.checkbox-grid label:hover{background:rgba(102,126,234,.12)}
.checkbox-grid input[type=checkbox]{accent-color:#667eea;width:13px;height:13px}
.help-text{font-size:10px;color:#888;margin-top:3px}
.badge{display:inline-block;padding:2px 6px;border-radius:5px;font-size:9px;font-weight:700}
.badge-mobile{background:rgba(37,211,102,.15);color:#25D366}
.badge-landline{background:rgba(255,193,7,.15);color:#ffc107}
.badge-verified{background:rgba(56,239,125,.15);color:#38ef7d}
.badge-guessed{background:rgba(255,193,7,.15);color:#ffc107}
.badge-apify{background:rgba(0,204,153,.2);color:#00cc99}
.badge-google{background:rgba(66,133,244,.2);color:#4285f4}
.wa-btn{display:inline-block;padding:3px 8px;border-radius:5px;font-size:10px;font-weight:700;background:#25D366;color:#fff;text-decoration:none;cursor:pointer}
.wa-btn:hover{background:#128C7E}
.optional-tag{font-size:9px;color:#888;background:rgba(255,255,255,.06);padding:1px 4px;border-radius:3px;margin-left:2px}
.section-label{font-size:12px;font-weight:700;color:#c9b1ff;margin-bottom:3px;display:block}
.footer{text-align:center;padding:20px;color:#555;font-size:10px}
</style>
</head>
<body>
<div class="header">
    <h1>AI Business Extractor + WhatsApp</h1>
    <p>Extract businesses with WhatsApp-ready mobile numbers</p>
    <span class="tag tag-green">WhatsApp Links</span>
    <span class="tag tag-blue">Google Maps</span>
    <span class="tag tag-purple">Apify</span>
    <span class="tag tag-blue">JustDial</span>
</div>
<div class="main">
    <div class="card">
        <h2>Configuration</h2>
        <div class="form-row">
            <div class="form-group">
                <label>Google Places API Key <span class="optional-tag">Optional if Apify</span></label>
                <input type="password" id="apiKey" placeholder="Google API key" autocomplete="off">
            </div>
            <div class="form-group">
                <label>Apify API Token <span class="optional-tag">Recommended</span></label>
                <input type="password" id="apifyKey" placeholder="Apify token" autocomplete="off">
                <div class="help-text"><a href="https://console.apify.com/account/integrations" target="_blank">Get free token</a></div>
            </div>
        </div>

        <label class="section-label">WhatsApp Message Template</label>
        <div class="form-group" style="max-width:600px">
            <textarea id="waMessage">Hi, I am reaching out from our company. We provide business solutions and services. Would you be interested in a quick discussion? Thank you!</textarea>
            <div class="help-text">This message will be pre-filled when you click WhatsApp links. Use {company} to insert business name.</div>
        </div>

        <br>
        <label class="section-label">Select Areas <a href="#" onclick="toggleAreas(true);return false" style="font-size:10px;font-weight:400">[All]</a> <a href="#" onclick="toggleAreas(false);return false" style="font-size:10px;font-weight:400">[None]</a></label>
        <div class="checkbox-grid" id="areaGrid"></div>

        <br>
        <label class="section-label">Select Categories</label>
        <div class="checkbox-grid" id="catGrid"></div>

        <div class="btn-row">
            <button class="btn btn-primary" id="extractBtn" onclick="startExtraction()">Extract Businesses</button>
            <button class="btn btn-success" id="downloadBtn" onclick="location.href='/download'" style="display:none">Download CSV</button>
            <button class="btn btn-whatsapp" id="downloadWaBtn" onclick="downloadWithWA()" style="display:none">Download CSV + WhatsApp Links</button>
            <button class="btn btn-danger" onclick="if(confirm('Clear history?')){fetch('/api/reset',{method:'POST'}).then(function(){location.reload()})}">Reset</button>
        </div>

        <div class="msg" id="msg"></div>

        <div class="stats" id="stats" style="display:none">
            <div class="stat-box"><div class="num" id="sNew">0</div><div class="lbl">New Businesses</div></div>
            <div class="stat-box"><div class="num" id="sSkipped">0</div><div class="lbl">Skipped</div></div>
            <div class="stat-box stat-wa"><div class="num" id="sWhatsApp">0</div><div class="lbl">WhatsApp Ready</div></div>
            <div class="stat-box"><div class="num" id="sMobile">0</div><div class="lbl">Mobile Numbers</div></div>
            <div class="stat-box"><div class="num" id="sEmails">0</div><div class="lbl">Emails</div></div>
            <div class="stat-box"><div class="num" id="sApify">0</div><div class="lbl">Apify</div></div>
            <div class="stat-box"><div class="num" id="sGoogle">0</div><div class="lbl">Google</div></div>
            <div class="stat-box"><div class="num" id="sJustDial">0</div><div class="lbl">JustDial</div></div>
        </div>
    </div>

    <div class="card" id="resultsCard" style="display:none">
        <h2>Results — Click WhatsApp to message directly</h2>
        <div class="table-wrap">
            <table><thead><tr>
                <th>#</th><th>Company</th><th>Phone</th><th>Type</th><th>WhatsApp</th>
                <th>Email</th><th>Website</th><th>Area</th><th>Rating</th><th>Source</th>
            </tr></thead><tbody id="resultsBody"></tbody></table>
        </div>
    </div>
</div>
<div class="footer">AI Business Extractor — Google + Apify + JustDial + WhatsApp</div>

<script>
var cats=CATEGORIES_PLACEHOLDER;
var areas=AREAS_PLACEHOLDER;
var catGrid=document.getElementById('catGrid');
Object.entries(cats).forEach(function(e){var k=e[0],v=e[1];var l=document.createElement('label');var chk=['it_companies','software','startups'].indexOf(k)>=0?'checked':'';l.innerHTML='<input type="checkbox" name="cat" value="'+k+'" '+chk+'> '+v.keyword;catGrid.appendChild(l)});
var areaGrid=document.getElementById('areaGrid');
areas.forEach(function(a,i){var l=document.createElement('label');var chk=i<10?'checked':'';l.innerHTML='<input type="checkbox" name="area" value="'+a+'" '+chk+'> '+a;areaGrid.appendChild(l)});

function toggleAreas(on){document.querySelectorAll('input[name=area]').forEach(function(c){c.checked=on})}
function showMsg(t,c){var m=document.getElementById('msg');m.className='msg show '+c;m.innerHTML=t}
function esc(s){if(!s)return'';var d=document.createElement('div');d.textContent=String(s);return d.innerHTML}

function startExtraction(){
    var apiKey=document.getElementById('apiKey').value.trim();
    var apifyKey=document.getElementById('apifyKey').value.trim();
    var waMessage=document.getElementById('waMessage').value.trim();
    if(!apiKey&&!apifyKey){showMsg('Enter at least one: Google API key or Apify token','error');return}
    var cats=[];document.querySelectorAll('input[name=cat]:checked').forEach(function(c){cats.push(c.value)});
    var areas=[];document.querySelectorAll('input[name=area]:checked').forEach(function(c){areas.push(c.value)});
    if(cats.length===0){showMsg('Select at least one category','error');return}
    if(areas.length===0){showMsg('Select at least one area','error');return}
    var btn=document.getElementById('extractBtn');btn.disabled=true;btn.textContent='Extracting...';
    document.getElementById('downloadBtn').style.display='none';
    document.getElementById('downloadWaBtn').style.display='none';
    document.getElementById('stats').style.display='none';
    document.getElementById('resultsCard').style.display='none';
    showMsg('Extracting across '+areas.length+' areas... This may take several minutes...','loading');

    fetch('/api/extract',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({apiKey:apiKey,apifyKey:apifyKey,categories:cats,areas:areas,waMessage:waMessage})
    }).then(function(r){return r.json()}).then(function(d){
        if(d.success){
            showMsg('Found <b>'+d.newBusinesses+'</b> new businesses! <b>'+d.whatsappReady+'</b> WhatsApp ready! (Apify:'+d.fromApify+' Google:'+d.fromGoogle+' JustDial:'+d.fromJustDial+')','success');
            document.getElementById('downloadBtn').style.display='inline-block';
            if(d.whatsappReady>0)document.getElementById('downloadWaBtn').style.display='inline-block';
            document.getElementById('stats').style.display='flex';
            document.getElementById('sNew').textContent=d.newBusinesses;
            document.getElementById('sSkipped').textContent=d.skipped;
            document.getElementById('sWhatsApp').textContent=d.whatsappReady;
            document.getElementById('sMobile').textContent=d.mobileNumbers;
            document.getElementById('sEmails').textContent=d.emailsFound;
            document.getElementById('sApify').textContent=d.fromApify;
            document.getElementById('sGoogle').textContent=d.fromGoogle;
            document.getElementById('sJustDial').textContent=d.fromJustDial;
            var tbody=document.getElementById('resultsBody');tbody.innerHTML='';
            d.businesses.forEach(function(b,i){var tr=document.createElement('tr');
                var phoneType=b.phone_type==='mobile'?'<span class="badge badge-mobile">Mobile</span>':b.phone_type==='landline'?'<span class="badge badge-landline">Landline</span>':'—';
                var waCell=b.whatsapp_link?'<a class="wa-btn" href="'+esc(b.whatsapp_link)+'" target="_blank">WhatsApp</a>':'—';
                var emailBadge=b.email_type==='verified'?'<span class="badge badge-verified">V</span> ':'';
                var src=b.source==='Apify'?'<span class="badge badge-apify">Apify</span>':b.source==='JustDial'?'<span class="badge badge-apify">JustDial</span>':'<span class="badge badge-google">Google</span>';
                tr.innerHTML='<td>'+(i+1)+'</td><td title="'+esc(b.company)+'">'+esc(b.company)+'</td><td>'+esc(b.phone)+'</td><td>'+phoneType+'</td><td>'+waCell+'</td><td>'+emailBadge+esc(b.email)+'</td><td>'+(b.website!=='N/A'?'<a href="'+esc(b.website)+'" target="_blank">Visit</a>':'—')+'</td><td>'+esc(b.area)+'</td><td>'+b.rating+'</td><td>'+src+'</td>';
                tbody.appendChild(tr)});
            document.getElementById('resultsCard').style.display='block';
        }else{showMsg('Error: '+d.message,'error')}
    }).catch(function(e){showMsg('Error: '+e.message,'error')})
    .finally(function(){btn.disabled=false;btn.textContent='Extract Businesses'});
}

function downloadWithWA(){
    var msg=encodeURIComponent(document.getElementById('waMessage').value.trim());
    location.href='/download?wa_message='+msg;
}
</script>
</body></html>
""".replace("CATEGORIES_PLACEHOLDER", CATS_JSON).replace("AREAS_PLACEHOLDER", AREAS_JSON)


# ============================================================
#  ROUTES
# ============================================================
@app.route("/")
def home():
    return render_template_string(HTML)

@app.route("/api/reset", methods=["POST"])
def reset():
    save_history({"extracted_ids": [], "run_count": 0, "total_extracted": 0})
    return jsonify({"success": True})

@app.route("/api/extract", methods=["POST"])
def extract():
    global extracted_businesses

    try:
        data = request.json
        api_key = data.get("apiKey", "").strip()
        apify_key = data.get("apifyKey", "").strip()
        categories = data.get("categories", [])
        selected_areas = data.get("areas", [])
        wa_message = data.get("waMessage", "")

        if not api_key and not apify_key:
            return jsonify({"success": False, "message": "Enter at least one key"})

        history = load_history()
        known_ids = set(history.get("extracted_ids", []))
        all_businesses = []
        skipped = 0

        # ---- APIFY ----
        if apify_key:
            search_queries = [CATEGORIES[c]["keyword"] for c in categories if c in CATEGORIES]
            for biz in extract_with_apify(apify_key, search_queries, selected_areas):
                biz_id = f"apify_{biz['company']}_{biz['phone']}"
                if biz_id in known_ids:
                    skipped += 1
                    continue
                known_ids.add(biz_id)
                if biz["whatsapp_link"] and wa_message:
                    msg = wa_message.replace("{company}", biz["company"])
                    biz["whatsapp_link"] = generate_whatsapp_link(biz["phone"], msg)
                all_businesses.append(biz)

        # ---- JUSTDIAL via Apify ----
        if apify_key:
            search_queries = [CATEGORIES[c]["keyword"] for c in categories if c in CATEGORIES]
            for biz in extract_from_justdial(apify_key, search_queries, selected_areas):
                biz_id = f"jd_{biz['company']}_{biz['phone']}"
                if biz_id in known_ids:
                    skipped += 1
                    continue
                known_ids.add(biz_id)
                if biz["whatsapp_link"] and wa_message:
                    msg = wa_message.replace("{company}", biz["company"])
                    biz["whatsapp_link"] = generate_whatsapp_link(biz["phone"], msg)
                all_businesses.append(biz)

        # ---- GOOGLE ----
        if api_key:
            seen = set()
            raw = []
            for area_name in selected_areas:
                coords = HYDERABAD_AREAS.get(area_name)
                if not coords:
                    continue
                lat, lng = coords
                for cat_key in categories:
                    cat = CATEGORIES.get(cat_key)
                    if not cat:
                        continue
                    print(f"  [Google] {area_name} -> {cat['keyword']}")
                    for p in google_nearby_search(api_key, lat, lng, cat["keyword"], cat["type"], 1):
                        pid = p.get("place_id")
                        if not pid or pid in seen or pid in known_ids:
                            if pid in known_ids:
                                skipped += 1
                            continue
                        seen.add(pid)
                        p["_area"] = area_name
                        raw.append(p)

            if raw:
                print(f"  [Google] Enriching {len(raw)} businesses...")
                with ThreadPoolExecutor(max_workers=6) as pool:
                    futures = {pool.submit(enrich_google_place, api_key, p, p.get("_area", "")): p for p in raw}
                    for f in as_completed(futures):
                        try:
                            biz = f.result()
                            if biz:
                                known_ids.add(futures[f].get("place_id", ""))
                                # Add WA message
                                if biz["whatsapp_link"] and wa_message:
                                    msg = wa_message.replace("{company}", biz["company"])
                                    biz["whatsapp_link"] = generate_whatsapp_link(biz["phone"], msg)
                                all_businesses.append(biz)
                        except Exception as exc:
                            print(f"  [WARN] {exc}")

        # Sort: WhatsApp-ready first, then by reviews
        all_businesses.sort(key=lambda x: (1 if x.get("whatsapp_link") else 0, x.get("reviews", 0)), reverse=True)
        extracted_businesses = all_businesses

        # Update history
        history["extracted_ids"] = list(known_ids)
        history["run_count"] = history.get("run_count", 0) + 1
        history["total_extracted"] = len(known_ids)
        save_history(history)

        # Stats
        mobile = sum(1 for b in all_businesses if b.get("phone_type") == "mobile")
        wa_ready = sum(1 for b in all_businesses if b.get("whatsapp_link"))
        emails = sum(1 for b in all_businesses if b.get("email", "N/A") != "N/A")
        from_apify = sum(1 for b in all_businesses if b.get("source") == "Apify")
        from_google = sum(1 for b in all_businesses if b.get("source") == "Google Places")
        from_justdial = sum(1 for b in all_businesses if b.get("source") == "JustDial")

        print(f"\n[DONE] {len(all_businesses)} new | {wa_ready} WhatsApp | Apify:{from_apify} Google:{from_google} JustDial:{from_justdial}\n")

        return jsonify({
            "success": True,
            "newBusinesses": len(all_businesses),
            "skipped": skipped,
            "whatsappReady": wa_ready,
            "mobileNumbers": mobile,
            "emailsFound": emails,
            "fromApify": from_apify,
            "fromGoogle": from_google,
            "fromJustDial": from_justdial,
            "businesses": all_businesses,
        })

    except Exception as e:
        print(f"[ERROR] {e}")
        return jsonify({"success": False, "message": str(e)})


@app.route("/download")
def download():
    global extracted_businesses
    if not extracted_businesses:
        return "No data.", 400

    wa_message = request.args.get("wa_message", "")

    si = StringIO()
    fields = ["company","address","phone","phone_type","whatsapp_link","email","email_type",
              "website","rating","reviews","status","area","maps_link",
              "social_facebook","social_instagram","social_linkedin","source"]
    writer = csv.DictWriter(si, fieldnames=fields)
    writer.writeheader()

    for biz in extracted_businesses:
        row = {k: biz.get(k, "") for k in fields}
        # Regenerate WA link with message if provided
        if wa_message and biz.get("phone_type") == "mobile":
            msg = wa_message.replace("{company}", biz.get("company", ""))
            row["whatsapp_link"] = generate_whatsapp_link(biz["phone"], msg)
        writer.writerow(row)

    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = f"attachment; filename=business_whatsapp_{int(time.time())}.csv"
    output.headers["Content-type"] = "text/csv; charset=utf-8"
    return output


def open_browser():
    time.sleep(2)
    try:
        webbrowser.open("http://localhost:5000")
    except Exception:
        pass

if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("  AI Business Extractor + WhatsApp")
    print("  Google + Apify + WhatsApp Links")
    print("=" * 60)
    print(f"  Apify: {'Ready' if APIFY_AVAILABLE else 'NOT installed (pip install apify-client)'}")
    print(f"\n  Server: http://localhost:5000")
    print("  Keep this window open!")
    print("=" * 60 + "\n")
    threading.Thread(target=open_browser, daemon=True).start()
    app.run(debug=False, port=5000, use_reloader=False, threaded=True)
