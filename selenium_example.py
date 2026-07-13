# selenium_example.py — Headless HTML review parser client

import sys
import httpx

# Example python client to send raw HTML to our backend for review analysis.
# This works headlessly and lets you scrape page source via Selenium or BeautifulSoup
# while browsing.

BACKEND_URL = "http://localhost:8000"

def analyze_raw_html(html_content: str, url: str = None):
    """
    Sends raw page HTML source to the backend.
    The backend uses BeautifulSoup to extract the reviews, product metadata,
    runs the NLP pipeline, caches it in SQLite, and returns the analysis.
    """
    try:
        response = httpx.post(
            f"{BACKEND_URL}/analyze/html",
            json={
                "html": html_content,
                "url": url,
                "aspects": []
            },
            timeout=60.0
        )
        if response.status_code != 200:
            print(f"Error {response.status_code}: {response.text}")
            return None
        return response.json()
    except Exception as e:
        print(f"Request failed: {e}")
        return None

if __name__ == "__main__":
    # Example usage:
    # Just read a saved html file and send it
    import argparse
    parser = argparse.ArgumentParser(description="Analyze saved Amazon product HTML.")
    parser.add_argument("html_file", help="Path to the saved HTML file")
    parser.add_argument("--url", help="Product page URL (optional, helps identify ASIN)", default=None)
    args = parser.parse_args()

    try:
        with open(args.html_file, "r", encoding="utf-8") as f:
            html_data = f.read()
        
        print("Sending HTML to backend for parsing and analysis...")
        result = analyze_raw_html(html_data, args.url)
        if result:
            print("\nAnalysis successful!")
            print(f"Product: {result['product']['name']} ({result['product']['asin']})")
            print(f"Total Reviews Found: {result['total_reviews']}")
            print(f"Sentiment Split: {result['sentiment_distribution']}")
            print(f"Verdict: {result['verdict']}")
            print(f"Summary: {result['summary']}")
    except FileNotFoundError:
        print(f"File not found: {args.html_file}")
