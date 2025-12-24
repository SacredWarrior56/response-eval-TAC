
# Deployment Guide for DigitalOcean Droplet (Ubuntu 24.04)

This guide helps you deploy the Agent Scraper Control Center on your 1 vCPU / 2GB RAM Droplet.

## 1. System Setup
SSH into your droplet:
```bash
ssh root@your_droplet_ip
```

Update system and install dependencies:
```bash
apt update && apt upgrade -y
apt install -y python3-pip python3-venv git
```

## 2. Clone Repository
```bash
git clone <your-repo-url> /opt/response-eval-TAC
cd /opt/response-eval-TAC
```

## 3. Environment Setup
Create virtual environment:
```bash
python3 -m venv venv
source venv/bin/activate
```

Install Python dependencies:
```bash
pip install -r requirements.txt
pip install playwright
playwright install --with-deps chromium
```

Create `.env` file:
```bash
nano .env
```
Paste your environment variables (OPENAI_KEY, HYPERBROWSER_API_KEY, Postgres config, etc.).

## 4. Database Setup
The application code handles `metadata` column migration automatically on first run. Ensure your Postgres coordinates in `.env` are correct.

## 5. Running as a Service (Systemd)
To ensure the Streamlit UI runs continuously on port 8501:

Create a service file:
```bash
nano /etc/systemd/system/scraper_ui.service
```

Paste the following content:
```ini
[Unit]
Description=Streamlit Scraper UI
After=network.target

[Service]
User=root
WorkingDirectory=/opt/response-eval-TAC
ExecStart=/opt/response-eval-TAC/venv/bin/streamlit run streamlit_app.py --server.port 8501 --server.address 0.0.0.0
Restart=always

[Install]
WantedBy=multi-user.target
```

Enable and Start:
```bash
systemctl daemon-reload
systemctl enable scraper_ui
systemctl start scraper_ui
```

Check status:
```bash
systemctl status scraper_ui
```

## 6. Accessing the UI
Open your browser and visit:
`http://<DROPLET_IP>:8501`

## 7. Operational Nuances
- **Persistent Execution**: When you click "Start Execution", a separate background process (`backend_runner.py`) is spawned. Even if you close the browser or restart the Streamlit service, the scraper continues running until completion.
- **Monitoring**: Any user accessing the URL will see the live progress of the currently active run.
- **Termination**: Use the "Terminate Run" button in the UI to safely stop the background process.

## 8. Troubleshotting
View logs:
```bash
journalctl -u scraper_ui -f
```
Or check the application logs if defined.
