import arxiv
import datetime
import requests


def get_arxiv_ai_papers(days_ago=3):
    """
    Fetches arXiv cs.AI articles published within the last `days_ago` days.
    Returns a list of dicts with title, authors, summary, published, url, pdf_url.
    """
    end_date = datetime.datetime.now(datetime.timezone.utc)
    start_date = end_date - datetime.timedelta(days=days_ago)
    
    search = arxiv.Search(
        query="cat:cs.AI",
        max_results=None,
        sort_by=arxiv.SortCriterion.SubmittedDate,
        sort_order=arxiv.SortOrder.Descending
    )
    papers = []
    for result in search.results():
        published_date = result.published
        if published_date >= start_date:
            summary_cleaned = result.summary.replace('\n', ' ')
            papers.append({
                "title": result.title,
                "authors": [author.name for author in result.authors],
                "summary": summary_cleaned,
                "published": published_date.isoformat(),
                "url": result.entry_id,
                "pdf_url": result.pdf_url,
                "source": "arXiv"
            })
        else:
            # Since results are sorted by newest first, we can stop once we hit older articles
            break
    return papers


def get_biorxiv_medrxiv_ai_papers(days_ago=3, server='biorxiv'):
    """
    Fetches bioRxiv or medRxiv articles related to AI/ML published within the last `days_ago` days.
    Returns a list of dicts with title, authors, summary, published, url, pdf_url.
    
    Args:
        days_ago: Number of days to look back
        server: Either 'biorxiv' or 'medrxiv'
    """
    end_date = datetime.datetime.now()
    start_date = end_date - datetime.timedelta(days=days_ago)
    
    # Format dates for the API
    start_str = start_date.strftime('%Y-%m-%d')
    end_str = end_date.strftime('%Y-%m-%d')
    
    # Call the bioRxiv/medRxiv API
    url = f"https://api.biorxiv.org/details/{server}/{start_str}/{end_str}"
    response = requests.get(url)
    data = response.json()
    
    # Filter for AI/ML related papers
    ai_keywords = ['artificial intelligence', 'machine learning', 'deep learning', 
                  'neural network', 'ai ', 'ml ', 'nlp ', 'computer vision', 
                  'predictive model', 'data mining', 'large language model', 'LLM']
    
    papers = []
    for paper in data.get('collection', []):
        # Combine title and abstract for keyword search
        text = (paper.get('title', '') + ' ' + paper.get('abstract', '')).lower()
        
        # Check if any AI keywords are in the text
        if any(keyword in text for keyword in ai_keywords):
            # Format authors similar to arXiv format
            author_list = paper.get('authors', '').split('; ')
            
            papers.append({
                "title": paper.get('title', ''),
                "authors": author_list,
                "summary": paper.get('abstract', ''),
                "published": paper.get('date', ''),
                "url": f"https://www.{server}.org/content/{paper.get('doi')}" if paper.get('doi') else '',
                "pdf_url": f"https://www.{server}.org/content/{paper.get('doi')}.full.pdf" if paper.get('doi') else '',
                "source": server
            })
    
    return papers


def get_all_ai_papers(days_ago=3):
    """
    Fetches AI-related papers from arXiv, bioRxiv, and medRxiv.
    Returns a combined list of papers.
    """
    arxiv_papers = get_arxiv_ai_papers(days_ago)
    biorxiv_papers = get_biorxiv_medrxiv_ai_papers(days_ago, server='biorxiv')
    medrxiv_papers = get_biorxiv_medrxiv_ai_papers(days_ago, server='medrxiv')
    
    all_papers = arxiv_papers + biorxiv_papers + medrxiv_papers
    
    # Sort by published date, newest first
    all_papers.sort(key=lambda x: x['published'], reverse=True)
    
    return all_papers


if __name__ == "__main__":
    DAYS_TO_SEARCH = 3
    
    # Get papers from all sources
    all_papers = get_all_ai_papers(days_ago=DAYS_TO_SEARCH)
    print(f"Found {len(all_papers)} AI papers across all sources in the last {DAYS_TO_SEARCH} days.")
    
    # Count by source
    sources = {}
    for paper in all_papers:
        source = paper.get('source', 'unknown')
        sources[source] = sources.get(source, 0) + 1
    
    for source, count in sources.items():
        print(f"- {source}: {count} papers")
    
    # Print details for each paper
    for i, paper in enumerate(all_papers, 1):
        print("-" * 80)
        print(f"Article {i} ({paper['source']}):")
        print(f"  Title: {paper['title']}")
        print(f"  Authors: {', '.join(paper['authors'])}")
        print(f"  Published: {paper['published']}")
        print(f"  Summary: {paper['summary']}")
        print(f"  URL: {paper['url']}")
        if paper['pdf_url']:
            print(f"  PDF Link: {paper['pdf_url']}")