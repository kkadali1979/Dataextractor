# 🤖 AI Business Data Extractor + WhatsApp

AI-powered tool to extract business data from Hyderabad with **WhatsApp-ready phone numbers**, emails, and social media — using Google Maps + Apify + JustDial.

![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)
![Flask](https://img.shields.io/badge/Flask-Web_App-green.svg)
![WhatsApp](https://img.shields.io/badge/WhatsApp-Ready-25D366.svg)
![Apify](https://img.shields.io/badge/Apify-Integrated-00CC99.svg)

---

## ✨ Features

### 3 Data Sources
- **Google Places API** — Verified business listings, ratings, reviews, phone numbers
- **Apify Google Maps Scraper** — Emails, social media profiles, contact details
- **JustDial** (via Apify) — India's #1 local search with verified phone numbers

### WhatsApp Integration
- Auto-detects **mobile numbers** (WhatsApp-capable) vs landlines
- Generates **click-to-chat WhatsApp links** for every mobile number
- **Custom message template** with `{company}` placeholder
- One-click **"WhatsApp" button** per business in the results table
- **CSV export** includes WhatsApp links ready to click

### Smart Phone Handling
- Classifies every number as **Mobile** or **Landline**
- Standardizes all numbers to **+91XXXXXXXXXX** format
- If Google gives a landline, scrapes the website for mobile numbers
- Extracts additional phone numbers from business websites

### Email Finding (4 Layers)
- Layer 1: Deep website scraping (homepage + contact/about pages)
- Layer 2: Google search for company email
- Layer 3: JustDial email extraction
- Layer 4: Smart email pattern guessing (info@domain.com)

### Area-Wise Search
- **30 areas across Hyderabad** — HITEC City, Gachibowli, Secunderabad, Madhapur, and more
- Select specific areas or search all at once
- Results tagged with area name

### No Duplicates
- History file tracks all previously extracted businesses
- Every run gives you only **NEW businesses**
- Reset button to start fresh anytime

---

## 🚀 Quick Start

### Prerequisites
- **Python 3.8+** — [Download](https://www.python.org/downloads/) (check "Add to PATH")
- **Apify Token** (Recommended) — [Get free token](https://console.apify.com/account/integrations) ($5/month free)
- **Google Places API Key** (Optional) — [Get key](https://console.cloud.google.com) ($200/month free)

### Installation

```bash
# Option 1: Windows — Double-click
Download ZIP → Extract → Double-click run.bat

# Option 2: Manual
git clone https://github.com/YOUR_USERNAME/ai-business-extractor.git
cd ai-business-extractor
pip install flask requests beautifulsoup4 apify-client
python app_hyderabad.py
```

Then open `http://localhost:5000` in your browser.

---

## 📖 How to Use

1. **Paste your API keys** — Apify token and/or Google API key (at least one needed)
2. **Write your WhatsApp message** — Use `{company}` to auto-insert business name
3. **Select areas** — Choose which Hyderabad areas to search
4. **Select categories** — IT companies, restaurants, hospitals, etc.
5. Click **Extract Businesses**
6. Click the green **WhatsApp** button next to any business to message them
7. Click **Download CSV** to get all data with WhatsApp links

---

## 📊 Data You Get (CSV Columns)

| Column | Description | Source |
|--------|-------------|--------|
| company | Business name | Google / Apify / JustDial |
| address | Full address | Google / Apify / JustDial |
| phone | Phone number (+91 format) | All sources |
| phone_type | mobile / landline | Auto-detected |
| whatsapp_link | Click-to-chat wa.me link | Auto-generated for mobile |
| email | Email address(es) | Website scraping / JustDial |
| email_type | verified / guessed | System |
| website | Business website URL | All sources |
| rating | Rating (1-5) | Google / JustDial |
| reviews | Number of reviews | Google / JustDial |
| area | Hyderabad area name | Search area |
| social_facebook | Facebook page URL | Apify |
| social_instagram | Instagram URL | Apify |
| social_linkedin | LinkedIn page URL | Apify |
| source | Apify / Google / JustDial | System |

---

## 🔑 Getting API Keys

### Apify Token (Recommended — Free $5/month)
1. Go to [apify.com](https://apify.com) → Sign up free
2. Go to **Settings** → **Integrations**
3. Copy your **API Token**

### Google Places API Key (Optional)
1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create a project → Enable **Places API**
3. Create credentials → **API Key**

---

## 📍 Supported Areas (30 Hyderabad zones)

Central, Secunderabad, Kompally, Mehdipatnam, HITEC City, Gachibowli, Financial District, Kondapur, Uppal, LB Nagar, Hayathnagar, Nacharam, Alwal, Bollaram, Bowenpally, Miyapur, Shamshabad, Attapur, Rajendranagar, Tolichowki, Patancheru, Narsingi, Manikonda, Begumpet, Banjara Hills, Ameerpet, Tarnaka, Dilsukhnagar, Kukatpally, Madhapur

---

## 📁 Project Structure

```
ai-business-extractor/
├── run.bat                  # Windows one-click launcher
├── app_hyderabad.py         # Main application
├── README.md                # This file
└── extracted_history.json   # Auto-created — tracks extracted businesses
```

---

## ⚙️ Customization

### Change City
Edit coordinates in `app_hyderabad.py`:
```python
HYDERABAD_LAT = 17.3850    # Your city latitude
HYDERABAD_LNG = 78.4867    # Your city longitude
```

### Add New Area
Add to the `HYDERABAD_AREAS` dictionary:
```python
"New Area Name": (latitude, longitude),
```

### Add New Category
Add to the `CATEGORIES` dictionary:
```python
"your_category": {"keyword": "search term", "type": "establishment"},
```

---

## ⚠️ Legal & Compliance

- All data from publicly available sources (Google Maps, JustDial, business websites)
- Follow anti-spam laws when using WhatsApp for outreach
- Respect WhatsApp's terms — avoid bulk unsolicited messaging
- Tool intended for legitimate business research and networking

---

## 📄 License

MIT License
