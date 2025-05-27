# NewsAPI.ai Medical AI News Collector

This extension to the MedAI News Bot adds the ability to collect AI in medicine news from NewsAPI.ai, a powerful news aggregation API that provides access to a wide range of news sources.

## Setup

1. **Get a NewsAPI.ai API key**
   - Register at [https://newsapi.ai/register](https://newsapi.ai/register)
   - You can use the free tier to start, which gives you 100 API calls per day
   - Add your API key to your `.env` file:
   ```
   NEWSAPI_KEY=your_api_key_here
   ```

2. **Install required packages**
   ```
   pip install requests
   ```
   (The other required packages should already be installed for your existing news collector)

## Files

- **newsapi_ai_collector.py**: Standalone script to fetch medical AI news from NewsAPI.ai
- **newsapi_integration.py**: Integration script that fetches news and adds it to your Google Sheet

## Using the Scripts

### Standalone Collection

To run the NewsAPI.ai collector by itself:

```
python newsapi_ai_collector.py
```

This will:
- Search for AI in medicine news from the last 3 days
- Categorize them according to your existing category system
- Display the results in the console
- Optionally save them to a JSON file

### Integration with your Google Sheet

To add NewsAPI.ai articles to your existing workflow:

```
python newsapi_integration.py
```

This will:
- Fetch news articles from NewsAPI.ai
- Check for duplicates in your Google Sheet
- Use your LLM to generate summaries and assign projects
- Add them to today's worksheet in your Google Sheet

## Features

- **Category-based searching**: Uses your existing category system to find relevant news
- **Deduplication**: Avoids adding the same article multiple times
- **LLM enhancement**: Uses your existing LLM setup to generate bullet summaries and project assignments
- **Seamless integration**: Articles are added to your existing Google Sheet in the same format

## Combined Workflow

For a complete news collection process, you can run:

1. Your existing news_worker.py to collect from RSS feeds and arXiv/bioRxiv/medRxiv
2. newsapi_integration.py to add NewsAPI.ai articles

This gives you comprehensive coverage of both academic preprints and general news media related to AI in medicine.

## Customization

- Edit the `CATEGORY_SEARCH_TERMS` dictionary in newsapi_ai_collector.py to adjust the search terms for each category
- Change the `days_ago` parameter to look back further in time
- Modify the search query structure in the `get_news_for_category` function to refine results 