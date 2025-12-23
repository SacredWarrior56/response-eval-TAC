# Response Automation

Automated chatbot response scraper for CarTrade and other websites using HyperBrowser.

## Setup

1. Clone the repository:
git clone <your-repo-url>
cd response_automation

2. Create a virtual environment:
python -m venv myenv

3. Activate the virtual environment:
**Windows (PowerShell):**
.\myenv\Scripts\Activate.ps1
**Windows (Command Prompt):**
myenv\Scripts\activate.bat
**Linux/Mac:**
source myenv/bin/activate

4. Install dependencies:h
pip install -r requirements.txt

5. Install Playwright browsers:sh
playwright install

6. Create a `.env` file in the root directory or copy .env.example
HYPERBROWSER_API_KEY=your_api_key_here## Usage

Run the CarTrade scraper:
python core/scrapers/cartrade_scraper.py## Project Structure
