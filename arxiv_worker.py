import os, json, hashlib, datetime as dt
import arxiv
from google import generativeai  # Updated import to avoid namespace conflicts
import gspread, feedparser
from dotenv import load_dotenv; load_dotenv()
import logging
from arxiv_ai_collector import get_all_ai_papers
import re

SOURCES_SHEET_ID = "1yvr3G5RU7zE9DatsCZdMNKNlKWUf9dMpiXCDFPrcAQM"
RAW_SHEET_ID = os.environ["RAW_SHEET_ID"]

# --- PROJECTS (for LLM-based categorization) ---
PROJECTS_FILE = "projects.json"
try:
    with open(PROJECTS_FILE, "r", encoding="utf-8") as f:
        projects = json.load(f)
except Exception as e:
    logging.warning(f"Could not load {PROJECTS_FILE}: {e}")
    projects = {}
# 'projects' is now a dict: {project_name: description, ...}

# --- MEDICAL RELEVANCE KEYWORDS ---
MEDICAL_KEYWORDS = [
    # Clinical terms
    "patient", "clinic", "hospital", "doctor", "physician", "nurse", "medical", "medicine",
    "diagnosis", "treatment", "therapy", "therapeutic", "surgery", "surgical", "symptom",
    "disease", "disorder", "syndrome", "pathology", "condition", "illness", "ailment",
    "prognosis", "remission", "recovery", "rehabilitation", "care", "outpatient", "inpatient",
    
    # Medical specialties
    "cardiology", "neurology", "oncology", "pediatrics", "geriatrics", "psychiatry",
    "orthopedics", "gynecology", "urology", "dermatology", "ophthalmology", "radiology",
    "anesthesiology", "endocrinology", "gastroenterology", "hematology", "nephrology",
    "rheumatology", "pulmonology", "immunology",
    
    # Medical imaging
    "mri", "ct scan", "ultrasound", "x-ray", "radiograph", "imaging", "sonography",
    "tomography", "pet scan", "mammography", "fluoroscopy", "angiography",
    
    # Healthcare systems
    "healthcare", "health care", "health system", "medical record", "ehr", "emr", 
    "electronic health record", "telemedicine", "telehealth", "health insurance",
    
    # Clinical procedures
    "biopsy", "screening", "checkup", "operation", "procedure", "intervention",
    "transplant", "dialysis", "transfusion", "injection", "implant", "prosthesis",
    
    # Pharmaceutical
    "drug", "medication", "pharmaceutical", "prescription", "dosage", "clinical trial",
    "vaccine", "antibiotic", "antiviral", "analgesic", "sedative", "steroid",
    
    # Biomedical
    "biomedical", "biomedicine", "biology", "physiology", "anatomy", "biochemistry",
    "molecular biology", "cell biology", "genetics", "genomics", "proteomics",
    "dna", "rna", "protein", "enzyme", "receptor", "antibody", "hormone", "gene",
    "chromosome", "mutation", "genome", "microbiome", "pathogen", "bacteria", "virus",
    
    # Health metrics
    "mortality", "morbidity", "longevity", "life expectancy", "vital sign", "blood pressure",
    "heart rate", "temperature", "respiratory rate", "oxygen saturation", "bmi",
    "body mass index", "cholesterol", "glucose", "electrolyte",
    
    # Public health
    "public health", "epidemiology", "epidemic", "pandemic", "outbreak", "infectious disease",
    "prevention", "health policy", "sanitation", "vaccination", "immunization",
    
    # Mental health
    "mental health", "psychology", "psychiatric", "cognitive", "behavioral",
    "depression", "anxiety", "schizophrenia", "bipolar", "therapy", "counseling",
    
    # Body systems and organs
    "cardiovascular", "neurological", "respiratory", "digestive", "endocrine",
    "reproductive", "skeletal", "muscular", "immune", "lymphatic", "renal", "urinary",
    "heart", "brain", "lung", "liver", "kidney", "intestine", "stomach", "pancreas",
    "thyroid", "spleen", "bone", "muscle", "blood", "artery", "vein",
    
    # Common diseases and conditions
    "cancer", "diabetes", "hypertension", "stroke", "asthma", "copd", "arthritis",
    "alzheimer", "parkinson", "dementia", "infection", "inflammation", "obesity",
    "malnutrition", "allergy", "autoimmune", "genetic disease"
]

# Create a combined regex pattern for efficient keyword matching
MEDICAL_PATTERN = re.compile(r'\b(' + '|'.join(MEDICAL_KEYWORDS) + r')\b', re.IGNORECASE)

# --- CATEGORY SYSTEM ---
CATEGORY_SYSTEM = '''
Main Categories and Subcategories:

Clinical Applications
- Diagnostics & Prognostics: AI for disease detection, outcome prediction, and clinical decision support
- Treatment & Intervention: Personalized medicine, surgical robotics, treatment optimization
- Monitoring & Supportive Care: Mental health tools, wearables, remote monitoring, real-time alert systems

Healthcare Operations
- Administrative Automation: Patient flow, documentation, scheduling, billing
- Data Infrastructure: EMR integration, interoperability solutions, clinical data management
- Operational Excellence: Resource allocation, workflow optimization

Research & Development
- Drug Discovery & Development: Target identification, molecular design, clinical trial optimization
- Public Health & Epidemiology: Disease surveillance, outbreak modeling, population health

Evaluation & Implementation
- Model Assessment: Benchmarking, validation, evaluation frameworks specific to healthcare
- Explainability & Transparency: Interpretable models, clinical reasoning, trust-building mechanisms
- Integration Challenges: Implementation science, workflow integration, adoption strategies

Ethical & Societal Implications
- Equity & Fairness: Algorithmic bias, health disparities, inclusive design
- Privacy & Security: Patient data protection, cybersecurity, consent management
- Policy & Regulation: Guidelines, compliance frameworks, liability considerations
- Environmental Impact: Computational resource usage, sustainability concerns

Education & Workforce
- Clinician Education: AI literacy for healthcare professionals, training approaches
- Patient Education: Health literacy, AI-enabled health education, preventative medicine
- Workforce Transformation: Role evolution, new specialties, human-AI collaboration

Other
- All other articles that don't fit a specific category
'''

# --- MEDICAL SOURCES (Always relevant) ---
MEDICAL_SOURCES = [
    "lancet", "nejm", "jama", "bmj", "medicalxpress", "healthtech", "healthnews", 
    "healthday", "medscape", "webmd", "mayoclinic", "nih", "cdc", "who", "pubmed"
]

load_dotenv()
generativeai.configure(api_key=os.environ["GOOGLE_API_KEY"])
model = generativeai.GenerativeModel("gemini-2.5-flash-preview-04-17")

gc = gspread.service_account("service_account.json")

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s: %(message)s')
logging.info('Starting news worker...')

# --- FUNCTIONS ---
def is_directly_medical(text, source=None):
    """Use LLM to determine if content is directly medically relevant and of high quality."""
    prompt = f"""
    You are a medical AI research expert. Analyze this article and determine:
    1. Is this article of substantially high quality with very direct medical relevance such that a lab of medical AI researchers should be aware of it? Note that these medical AI researchers are mostly interested in cutting-edge AI research such as LLMs. 
    2. If yes, briefly describe the specific medical application or relevance (1-2 sentences).

    Return ONLY valid JSON with this format: 
    {{
        "is_directly_medical": true/false,
        "medical_application": "Description of medical relevance" (or null if not directly medical)
    }}

    Article: {text}
    """
    
    try:
        response = model.generate_content(prompt)
        text_response = response.text.strip()
        if text_response.startswith("```"):
            text_response = re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", text_response, flags=re.MULTILINE).strip()
        data = json.loads(text_response)
        return data.get("is_directly_medical", False), data.get("medical_application")
    except Exception as e:
        logging.error(f"Error checking direct medical relevance: {e}")
        return False, None



def generate_summary_and_category(article_text, application_context=None):
    """Generate summary, title, categorize an article, and assign to one or more projects."""
    # If we have application context, include it in the prompt
    context = ""
    if application_context:
        context = f"\nThis AI research has the following medical application: {application_context}\nPlease categorize based on this medical application. However, create a succinct 3-5 bullet point summary that is focussed on the article only."

    # Prepare project list for the LLM
    project_list = '\n'.join([f"- {name}: {desc}" for name, desc in projects.items()])
    
    prompt = (
        'Return ONLY valid JSON (no markdown, no explanation, no code block) with the following keys: '
        '{title, bullet_summary, main_category, subcategory, project} for the following article.\n'
        'bullet_summary should be a list of 1-3 concise bullet points, e.g.:\n'
        '{"bullet_summary": ["• Point 1", "• Point 2", "• Point 3"]}\n'
        '\n'
        'Here is a list of ongoing lab projects. Assign the article to all relevant projects by name (as a list), or use ["No News"] if it does not fit any specific project.\n'
        'For example: {"project": ["Project Alpha", "Project Beta"]} or {"project": ["No News"]}\n'
        f'{project_list}\n'
        '\n'
        f'{CATEGORY_SYSTEM}\n{context}\nArticle: """{article_text}"""'
    )
    
    try:
        response = model.generate_content(prompt)
        text = response.text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", text, flags=re.MULTILINE).strip()
        return json.loads(text)
    except Exception as e:
        logging.error(f"Error generating bullet_summary: {e}")
        return None

# --- SHEET MANAGEMENT ---
today_str = dt.date.today().isoformat()
try:
    today_ws = gc.open_by_key(RAW_SHEET_ID).worksheet(today_str)
    logging.info(f"Opened existing worksheet for today: {today_str}")
except gspread.exceptions.WorksheetNotFound:
    today_ws = gc.open_by_key(RAW_SHEET_ID).add_worksheet(title=today_str, rows="1000", cols="20")
    today_ws.append_row(["Source", "Main Category", "Subcategory", "Title", "Summary", "URL", "Scraped At", "Cross-domain", "Application Context", "Project"])
    logging.info(f"Created new worksheet for today: {today_str}")

# Store non-relevant articles at the bottom
non_relevant_urls = []

# Helper: get all URL hashes from the last N days' sheets
def get_recent_url_hashes(gc, raw_sheet_id, days=3):
    book = gc.open_by_key(raw_sheet_id)
    url_hashes = set()
    for i in range(days):
        date_str = (dt.date.today() - dt.timedelta(days=i)).isoformat()
        try:
            ws = book.worksheet(date_str)
            hashes = ws.col_values(6)  # URL column (will hash below)
            url_hashes.update(hashlib.sha256(url.encode()).hexdigest()[:12] for url in hashes if url)
            logging.info(f"Loaded {len(hashes)} URLs from sheet {date_str}")
        except gspread.exceptions.WorksheetNotFound:
            logging.info(f"No worksheet found for {date_str}, skipping.")
            continue
    logging.info(f"Total unique URL hashes from recent days: {len(url_hashes)}")
    return url_hashes

recent_url_hashes = get_recent_url_hashes(gc, RAW_SHEET_ID, days=3)

# --- PROCESS FEEDS ---
logging.info("Starting to process feeds from sources sheet...")
for row in gc.open_by_key(SOURCES_SHEET_ID).sheet1.get_all_records():
    source_name = row.get("source", "Unknown Source")
    logging.info(f"Fetching feed from {source_name}: {row['url']}")
    feed = feedparser.parse(row["url"])
    if not feed.entries:
        logging.info(f"No entries found for {row['url']}, skipping.")
        continue
    entry = feed.entries[0]
    url = entry.link
    url_hash = hashlib.sha256(url.encode()).hexdigest()[:12]
    if url_hash in recent_url_hashes:
        logging.info(f"Duplicate found for {url}, skipping.")
        continue
    
    article = entry.get("summary", entry.title)[:8000]
    
    # Check direct medical relevance using LLM
    is_medical, medical_application = is_directly_medical(article, source_name)
    logging.info(f"Article {'IS' if is_medical else 'IS NOT'} directly medically relevant.")
    
    # Only process articles that are directly medically relevant
    if is_medical:
        logging.info(f"Processing high-quality medical article: {url}")
        data = generate_summary_and_category(article, medical_application)
        if not data:
            continue
        # Format bullet_summary for Google Sheets
        bullet_summary = data["bullet_summary"]
        if isinstance(bullet_summary, list):
            bullet_summary = "\n".join(bullet_summary)
        # Format project list
        project_list = ', '.join(data.get("project", ["No News"]))
        today_ws.append_row([
            source_name,
            data.get("main_category", "Other"),
            data.get("subcategory", "Other"),
            data["title"],
            bullet_summary,
            url,
            dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "NO",  # Direct medical relevance
            medical_application or "",  # Medical application context
            project_list
        ])
        logging.info(f"Appended medical article to sheet: {url}")
    else:
        # Not directly medical - skip this article
        logging.info(f"Skipping non-medical article: {url}")
        non_relevant_urls.append(url)
    
    recent_url_hashes.add(url_hash)

# --- INTEGRATE AI PAPERS FROM MULTIPLE SOURCES ---
logging.info('Fetching AI papers from arXiv, bioRxiv, and medRxiv...')
all_papers = get_all_ai_papers(days_ago=3)
logging.info(f"Found {len(all_papers)} AI papers to process across all sources.")

# Count by source for logging
sources = {}
for paper in all_papers:
    source = paper.get('source', 'unknown')
    sources[source] = sources.get(source, 0) + 1

for source, count in sources.items():
    logging.info(f"- {source}: {count} papers")

for idx, paper in enumerate(all_papers):
    url = paper["url"]
    source = paper.get("source", "unknown")
    url_hash = hashlib.sha256(url.encode()).hexdigest()[:12]
    logging.info(f"Processing {source} paper {idx+1}/{len(all_papers)}: {url}")
    if url_hash in recent_url_hashes:
        logging.info(f"Duplicate found for {source} paper: {url}, skipping.")
        continue
        
    article = f"Title: {paper['title']}\nAuthors: {', '.join(paper['authors'])}\nAbstract: {paper['summary']}"[:8000]
    
    # Check direct medical relevance using LLM
    is_medical, medical_application = is_directly_medical(article, source)
    logging.info(f"{source} paper {'IS' if is_medical else 'IS NOT'} directly medically relevant.")
    
    # Only process papers that are directly medically relevant
    if is_medical:
        logging.info(f"Processing high-quality medical {source} paper: {url}")
        data = generate_summary_and_category(article, medical_application)
        if not data:
            continue
        # Format bullet_summary for Google Sheets
        bullet_summary = data["bullet_summary"]
        if isinstance(bullet_summary, list):
            bullet_summary = "\n".join(bullet_summary)
        # Format project list
        project_list = ', '.join(data.get("project", ["No News"]))
        today_ws.append_row([
            source,
            data.get("main_category", "Other"),
            data.get("subcategory", "Other"),
            paper["title"],
            bullet_summary,
            url,
            dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "NO",  # Direct medical relevance
            medical_application or "",  # Medical application context
            project_list
        ])
        logging.info(f"Appended medical {source} paper to sheet: {url}")
    else:
        # Not directly medical - skip this paper
        logging.info(f"Skipping non-medical {source} paper: {url}")
        non_relevant_urls.append(url)
    
    recent_url_hashes.add(url_hash)

# Add non-relevant URLs at the bottom of the sheet
#if non_relevant_urls:
#    logging.info(f"Adding {len(non_relevant_urls)} non-relevant URLs to the bottom of the sheet")
#    today_ws.append_row(["--- Non-Relevant Articles Below ---", "", "", "", "", "", "", "", "", ""])
#    for url in non_relevant_urls:
#        today_ws.append_row(["Non-relevant", "", "", "", "", url, dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "", "", ""])
