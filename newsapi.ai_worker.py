import os
import json
import logging
import datetime as dt
import time
import hashlib
from typing import List, Dict, Optional, Any
from dotenv import load_dotenv
from google import generativeai
import gspread
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s %(levelname)s: %(message)s',
    handlers=[
        logging.FileHandler('medical_ai_news.log'),
        logging.StreamHandler()
    ]
)

# Configure Google AI
try:
    generativeai.configure(api_key=os.environ["GOOGLE_API_KEY"])
    model = generativeai.GenerativeModel("gemini-2.5-flash-preview-04-17")
    logging.info("Google AI configured successfully")
except Exception as e:
    logging.error(f"Failed to configure Google AI: {e}")
    model = None

# Setup Google Sheets
try:
    gc = gspread.service_account("service_account.json")
    RAW_SHEET_ID = os.environ["RAW_SHEET_ID"]
    logging.info("Google Sheets configured successfully")
except Exception as e:
    logging.error(f"Failed to configure Google Sheets: {e}")
    gc = None

# NewsAPI.ai configuration
NEWSAPI_AI_KEY = os.environ.get("NEWSAPI_AI_KEY")
if not NEWSAPI_AI_KEY:
    raise ValueError(
        "NewsAPI.ai API key not found. Please add NEWSAPI_AI_KEY to your .env file. "
        "You can get a key at https://newsapi.ai/register"
    )

# Try to load projects for categorization
PROJECTS_FILE = "projects.json"
try:
    with open(PROJECTS_FILE, "r", encoding="utf-8") as f:
        projects = json.load(f)
    logging.info(f"Loaded {len(projects)} projects from {PROJECTS_FILE}")
except Exception as e:
    logging.warning(f"Could not load {PROJECTS_FILE}: {e}")
    projects = {}

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

# OPTIMIZED SEARCH TERMS - Based on performance analysis from logs
# Focused on high-yield queries that actually return quality medical AI articles
MEDICAL_AI_SEARCH_TERMS = [
    # TOP PERFORMERS (proven to return quality articles)
    "AI healthcare",           # 8 articles - highest quality, real implementations
    "AI drug discovery",       # 6 articles - strong R&D focus with timelines
    "AI diagnosis",            # 3 articles - clinical focus, practical applications
    "AI radiology",           # 1 article - medical specialty applications  
    "AI pathology",           # 1 article - medical specialty applications
    
    # STRATEGIC ADDITIONS (likely high-yield based on successful patterns)
    "AI surgery",             # Medical procedure focus, follows successful pattern
    "clinical AI",            # Clinical implementation focus
    "medical artificial intelligence"  # Formal variation of successful terms
]

class NewsAPICollector:
    """NewsAPI.ai collector for medical AI content."""
    
    def __init__(self):
        self.api_key = NEWSAPI_AI_KEY
        self.base_url = "https://newsapi.ai/api/v1/article/getArticles"
        self.session = self._create_session()
        self.cache = {}
        self.rate_limit_delay = 1.0
        self.last_request_time = 0
        
    def _create_session(self) -> requests.Session:
        """Create a requests session with retry strategy."""
        session = requests.Session()
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        return session
    
    def _rate_limit(self):
        """Implement rate limiting to avoid API limits."""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        if time_since_last < self.rate_limit_delay:
            time.sleep(self.rate_limit_delay - time_since_last)
        self.last_request_time = time.time()
    
    def _make_request(self, params: Dict[str, Any]) -> Optional[Dict]:
        """Make API request with proper error handling."""
        self._rate_limit()
        
        # Check cache first
        cache_key = hashlib.md5(str(sorted(params.items())).encode()).hexdigest()
        if cache_key in self.cache:
            logging.info("Using cached result")
            return self.cache[cache_key]
        
        try:
            response = self.session.get(self.base_url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            # Cache the result
            self.cache[cache_key] = data
            return data
            
        except requests.exceptions.Timeout:
            logging.error("Request timeout")
            return None
        except requests.exceptions.RequestException as e:
            logging.error(f"Request error: {e}")
            return None
        except json.JSONDecodeError as e:
            logging.error(f"JSON decode error: {e}")
            return None
    
    def _calculate_medical_relevance(self, article: Dict) -> float:
        """Calculate how relevant an article is to medical AI (0-1 score)."""
        title = article.get('title', '').lower()
        content = article.get('summary', '').lower()
        combined_text = f"{title} {content}"
        
        # High-value medical AI terms
        high_value_terms = [
            'medical ai', 'clinical ai', 'healthcare ai', 'ai diagnosis', 'ai treatment',
            'ai drug discovery', 'ai clinical trial', 'medical machine learning',
            'ai radiology', 'ai pathology', 'ai surgery', 'clinical decision support',
            'ai electronic health', 'medical imaging ai', 'ai healthcare', 'fda approval',
            'clinical validation', 'ai medical device', 'healthcare artificial intelligence',
            'medgemma', 'medical breakthrough'
        ]
        
        # Medium-value terms
        medium_value_terms = [
            'hospital', 'patient', 'doctor', 'physician', 'clinical', 'medical',
            'healthcare', 'diagnosis', 'treatment', 'pharmaceutical', 'drug'
        ]
        
        # Negative terms (reduce relevance)
        negative_terms = [
            'soccer', 'football', 'sports', 'gaming', 'entertainment', 'movie',
            'celebrity', 'fashion', 'politics', 'election', 'war', 'military'
        ]
        
        score = 0.0
        
        # High-value term matching (each worth 0.3)
        for term in high_value_terms:
            if term in combined_text:
                score += 0.3
        
        # Medium-value term matching (each worth 0.1)
        for term in medium_value_terms:
            if term in combined_text:
                score += 0.1
        
        # Penalty for negative terms
        for term in negative_terms:
            if term in combined_text:
                score -= 0.5
        
        # Bonus for AI + medical combination
        has_ai = ('ai' in combined_text or 'artificial intelligence' in combined_text or 'machine learning' in combined_text)
        has_medical = any(term in combined_text for term in ['medical', 'healthcare', 'clinical', 'patient', 'hospital'])
        
        if has_ai and has_medical:
            score += 0.4
        
        return max(0.0, min(1.0, score))
    
    def _calculate_recency_score(self, article: Dict) -> float:
        """Calculate recency score (0-1, where 1 = most recent)."""
        try:
            pub_date_str = article.get('published', '')
            if 'T' in pub_date_str:
                pub_date = dt.datetime.fromisoformat(pub_date_str.replace('Z', '+00:00'))
            else:
                pub_date = dt.datetime.fromisoformat(pub_date_str)
            
            now = dt.datetime.now(dt.timezone.utc)
            hours_ago = (now - pub_date.replace(tzinfo=dt.timezone.utc)).total_seconds() / 3600
            
            # Recency scoring
            if hours_ago <= 6:
                return 1.0
            elif hours_ago <= 24:
                return 0.8
            elif hours_ago <= 48:
                return 0.6
            elif hours_ago <= 72:
                return 0.4
            else:
                return 0.2
                
        except Exception as e:
            logging.warning(f"Error calculating recency score: {e}")
            return 0.5
    
    def _calculate_combined_score(self, article: Dict) -> float:
        """Calculate combined relevance + recency score."""
        relevance_score = self._calculate_medical_relevance(article)
        recency_score = self._calculate_recency_score(article)
        
        # 70% relevance, 30% recency
        combined_score = (0.7 * relevance_score) + (0.3 * recency_score)
        return combined_score
    
    def get_medical_ai_news(self, days_ago: int = 3) -> List[Dict]:
        """Get medical AI news with proper search strategy."""
        all_articles = []
        
        # Calculate date range
        end_date = dt.datetime.now()
        start_date = end_date - dt.timedelta(days=days_ago)
        date_from = start_date.strftime('%Y-%m-%d')
        date_to = end_date.strftime('%Y-%m-%d')
        
        logging.info(f"OPTIMIZED SEARCH: Using {len(MEDICAL_AI_SEARCH_TERMS)} high-yield queries (reduced from 19)")
        logging.info(f"Expected cost reduction: ~57% fewer API calls")
        
        # Search with optimized, high-yield terms only
        for query in MEDICAL_AI_SEARCH_TERMS:
            logging.info(f"Searching for: {query}")
            
            # Use the parameters that work with Event Registry/NewsAPI.ai
            params = {
                'apiKey': self.api_key,
                'resultType': 'articles',
                'keyword': query,  # Use keyword instead of q
                'lang': 'eng',
                'dateStart': date_from,
                'dateEnd': date_to,
                'articlesSortBy': 'date',  # Sort by date for latest first
                'articlesCount': 30,  # Get more results
                'includeArticleCategories': True,
                'includeArticleImage': True,
                'includeSourceTitle': True
            }
            
            data = self._make_request(params)
            if not data:
                continue
            
            # Parse articles
            articles = []
            if 'articles' in data and 'results' in data['articles']:
                for article in data['articles']['results']:
                    try:
                        title = article.get('title', '').strip()
                        if not title:
                            continue
                        
                        # Get full article content - try multiple fields
                        content = (
                            article.get('body', '') or 
                            article.get('content', '') or 
                            article.get('description', '') or
                            article.get('snippet', '') or
                            article.get('text', '')
                        ).strip()
                        
                        # If content is too short, log for debugging
                        if len(content) < 100:
                            logging.warning(f"Short content ({len(content)} chars) for: {title[:50]}...")
                            logging.debug(f"Available content fields: {list(article.keys())}")
                        
                        url = article.get('url', '').strip()
                        if not url:
                            continue
                        
                        # Get source info
                        source_info = article.get('source', {})
                        source_name = source_info.get('title', 'Unknown') if isinstance(source_info, dict) else str(source_info)
                        
                        # Get publication date
                        pub_date = article.get('dateTime', dt.datetime.now().isoformat())
                        
                        # Get authors
                        authors = article.get('authors', [])
                        if not authors:
                            authors = ['Unknown']
                        elif isinstance(authors, list) and len(authors) > 0:
                            # Extract author names if it's a list of dicts
                            author_names = []
                            for author in authors:
                                if isinstance(author, dict):
                                    author_names.append(author.get('name', 'Unknown'))
                                else:
                                    author_names.append(str(author))
                            authors = author_names
                        
                        article_data = {
                            "title": title,
                            "authors": authors,
                            "summary": content,
                            "published": pub_date,
                            "url": url,
                            "source": source_name,
                            "search_query": query,
                            "main_category": "To be determined",
                            "subcategory": "To be determined"
                        }
                        
                        # Calculate scores
                        relevance_score = self._calculate_medical_relevance(article_data)
                        recency_score = self._calculate_recency_score(article_data)
                        combined_score = self._calculate_combined_score(article_data)
                        
                        article_data['relevance_score'] = relevance_score
                        article_data['recency_score'] = recency_score
                        article_data['combined_score'] = combined_score
                        
                        # Lower threshold to catch more articles
                        if relevance_score >= 0.2 or (relevance_score >= 0.1 and recency_score >= 0.8):
                            articles.append(article_data)
                            
                    except Exception as e:
                        logging.warning(f"Error parsing article: {e}")
                        continue
            
            all_articles.extend(articles)
            logging.info(f"Found {len(articles)} relevant articles for '{query}' (API call {MEDICAL_AI_SEARCH_TERMS.index(query) + 1}/{len(MEDICAL_AI_SEARCH_TERMS)})")
        
        # Remove duplicates
        seen_urls = set()
        unique_articles = []
        for article in all_articles:
            if article['url'] not in seen_urls:
                seen_urls.add(article['url'])
                unique_articles.append(article)
        
        # Sort by combined score
        unique_articles.sort(key=lambda x: x['combined_score'], reverse=True)
        
        # Take top 40 articles
        top_articles = unique_articles[:40]
        
        logging.info(f"OPTIMIZATION RESULTS: {len(top_articles)} articles from {len(all_articles)} total using {len(MEDICAL_AI_SEARCH_TERMS)} API calls")
        logging.info(f"Previous approach would have used 19 API calls - saved {19 - len(MEDICAL_AI_SEARCH_TERMS)} calls ({((19 - len(MEDICAL_AI_SEARCH_TERMS))/19*100):.0f}% reduction)")
        
        if top_articles:
            avg_relevance = sum(a['relevance_score'] for a in top_articles) / len(top_articles)
            avg_recency = sum(a['recency_score'] for a in top_articles) / len(top_articles)
            avg_combined = sum(a['combined_score'] for a in top_articles) / len(top_articles)
            
            logging.info(f"Quality metrics - Relevance: {avg_relevance:.2f}, Recency: {avg_recency:.2f}, Combined: {avg_combined:.2f}")
            
            recent_count = sum(1 for a in top_articles if a['recency_score'] >= 0.8)
            logging.info(f"Recent articles (<24h): {recent_count}/{len(top_articles)}")
        
        return top_articles

def generate_summary_and_category(article_text: str, application_context: Optional[str] = None) -> Optional[Dict]:
    """Generate summary, categorize an article, and assign to one or more projects."""
    if not model:
        logging.error("Google AI model not available")
        return None
    
    context = ""
    if application_context:
        context = f"\nApplication: {application_context}"

    project_list = '\n'.join([f"- {name}: {desc}" for name, desc in projects.items()])
    
    # Simplified prompt for better JSON generation
    prompt = f'''Analyze this medical AI article and return valid JSON:

{{
  "title": "Brief title",
  "bullet_summary": ["• Point 1", "• Point 2", "• Point 3"],
  "main_category": "Clinical Applications",
  "subcategory": "Diagnostics & Prognostics", 
  "project": ["Project Name"]
}}

Categories: {CATEGORY_SYSTEM}

Projects: {project_list}
Use ["No News"] if no projects fit.{context}

Article: {article_text[:3000]}'''
    
    try:
        response = model.generate_content(prompt)
        text = response.text.strip()
        
        # Clean response
        if text.startswith("```"):
            import re
            text = re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", text, flags=re.MULTILINE).strip()
        
        result = json.loads(text)
        
        # Validate
        required_keys = ['title', 'bullet_summary', 'main_category', 'subcategory', 'project']
        if not all(key in result for key in required_keys):
            return None
        
        return result
        
    except Exception as e:
        logging.error(f"Error generating summary: {e}")
        return None

def process_newsapi_articles(days_ago: int = 3) -> int:
    """Process articles from NewsAPI.ai."""
    if not gc:
        logging.error("Google Sheets not configured")
        return 0
    
    collector = NewsAPICollector()
    
    logging.info("Fetching medical AI articles...")
    articles = collector.get_medical_ai_news(days_ago=days_ago)
    logging.info(f"Found {len(articles)} articles")
    
    if not articles:
        logging.warning("No articles found")
        return 0
    
    # Setup worksheet
    today_str = dt.date.today().isoformat()
    try:
        today_ws = gc.open_by_key(RAW_SHEET_ID).worksheet(today_str)
        logging.info(f"Opened existing worksheet: {today_str}")
    except gspread.exceptions.WorksheetNotFound:
        today_ws = gc.open_by_key(RAW_SHEET_ID).add_worksheet(title=today_str, rows="1000", cols="20")
        headers = [
            "Source", "Main Category", "Subcategory", "Title", "Summary", 
            "URL", "Scraped At", "Cross-domain", "Application Context", "Project"
        ]
        today_ws.append_row(headers)
        logging.info(f"Created new worksheet: {today_str}")
    
    # Get existing URLs
    existing_urls = set()
    try:
        urls = today_ws.col_values(6)  # URL column
        existing_urls = set(urls[1:])  # Skip header
        logging.info(f"Found {len(existing_urls)} existing URLs")
    except Exception as e:
        logging.warning(f"Error getting existing URLs: {e}")
    
    # Process articles
    processed_count = 0
    for idx, article in enumerate(articles):
        url = article["url"]
        if url in existing_urls:
            logging.info(f"Skipping duplicate: {url}")
            continue
        
        logging.info(f"Processing {idx+1}/{len(articles)}: {article['title'][:50]}... (score: {article['combined_score']:.2f})")
        
        # Prepare for LLM
        article_text = f"Title: {article['title']}\nContent: {article['summary']}"[:3000]
        
        # Get categorization
        data = generate_summary_and_category(article_text)
        if not data:
            logging.warning(f"Failed to categorize: {url}")
            data = {
                'title': article['title'],
                'bullet_summary': [f"• {article['summary'][:200]}..."],
                'main_category': 'Other',
                'subcategory': 'Other',
                'project': ['No News']
            }
        
        # Format for sheets
        bullet_summary = data["bullet_summary"]
        if isinstance(bullet_summary, list):
            bullet_summary = "\n".join(bullet_summary)
        
        project_list = ', '.join(data.get("project", ["No News"]))
        cross_domain = "NO" if article['combined_score'] >= 0.6 else "YES"
        
        # Add to worksheet
        try:
            row_data = [
                article["source"],
                data.get("main_category", "Other"),
                data.get("subcategory", "Other"),
                article["title"],
                bullet_summary,
                url,
                dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                cross_domain,
                "",
                project_list
            ]
            
            today_ws.append_row(row_data)
            processed_count += 1
            logging.info(f"ADDED: {article['title'][:50]}... (rel: {article['relevance_score']:.2f}, rec: {article['recency_score']:.2f})")
            
        except Exception as e:
            logging.error(f"Error adding to worksheet: {e}")
            continue
    
    logging.info(f"Successfully processed {processed_count} articles")
    return processed_count

def main():
    """Main function."""
    DAYS_TO_SEARCH = 3
    
    logging.info("Starting OPTIMIZED Medical AI News Collection")
    logging.info(f"Using {len(MEDICAL_AI_SEARCH_TERMS)} proven high-yield search terms")
    logging.info(f"Searching last {DAYS_TO_SEARCH} days")
    
    try:
        count = process_newsapi_articles(days_ago=DAYS_TO_SEARCH)
        print(f"Successfully added {count} medical AI articles using optimized search strategy.")
        logging.info(f"OPTIMIZATION SUCCESS: Added {count} articles with {len(MEDICAL_AI_SEARCH_TERMS)} API calls instead of 19.")
        
    except Exception as e:
        error_msg = f"Error: {e}"
        print(error_msg)
        logging.error(error_msg)
        raise

if __name__ == "__main__":
    main()