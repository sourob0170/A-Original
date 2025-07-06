## Deployment Instructions (Heroku)

Follow these steps to deploy Aeon to Heroku:

### 1. Fork and Star the Repository
- Click the **Fork** button at the top-right corner of this repository.
- Give the repository a star to show your support.

### 2. Navigate to Your Forked Repository
- Access your forked version of this repository.

### 3. Enable GitHub Actions
- Go to the **Settings** tab of your forked repository.
- Enable **Actions** by selecting the appropriate option in the settings.

### 4. Run the Deployment Workflow
1. Open the **Actions** tab.
2. Select the `Deploy to Heroku` workflow from the available list.
3. Click **Run workflow** and fill out the required inputs:
   - **BOT_TOKEN**: Your Telegram bot token.
   - **OWNER_ID**: Your Telegram ID.
   - **DATABASE_URL**: MongoDB connection string.
   - **TELEGRAM_API**: Telegram API ID (from [my.telegram.org](https://my.telegram.org/)).
   - **TELEGRAM_HASH**: Telegram API hash (from [my.telegram.org](https://my.telegram.org/)).
   - **HEROKU_APP_NAME**: Name of your Heroku app.
   - **HEROKU_EMAIL**: Email address associated with your Heroku account.
   - **HEROKU_API_KEY**: API key from your Heroku account.
   - **HEROKU_TEAM_NAME** (Optional): Required only if deploying under a Heroku team account.
4. Run the workflow and wait for it to complete.

### 5. Finalize Setup
- After deployment, configure any remaining variables in your Heroku dashboard.
- Use the `/botsettings` command to upload sensitive files like `token.pickle` if needed.

---

## Deployment Instructions (VPS)

Follow these steps to deploy Aeon to VPS:

### 1. Star the Repository
- Give the repository a star to show your support.

### 2. Clone The Repository
- Clone the repository to your VPS.

```
git clone https://github.com/AeonOrg/Aeon-MLTB.git && cd Aeon-MLTB && git checkout extended
```

### 3. Install Requirements

- For Debian based distros

```
sudo apt install python3 python3-pip
```

Install Docker by following the [official Docker docs](https://docs.docker.com/engine/install/debian/)

- For Arch and it's derivatives:

```
sudo pacman -S docker python
```

- Install dependencies for running setup scripts:

```
pip3 install -r dev/requirements-cli.txt
```

### 4. Setting up config file

```
cp config_sample.py config.py
```

Fill up all the required fields.


### 5. Run the bot

#### Using Docker Compose Plugin

- Install docker compose plugin

```
sudo apt install docker-compose-plugin
```

- Build and run Docker image:

```
sudo docker compose up
```

- After editing files with nano, for example (nano start.sh) or git pull you must use --build to edit container files:

```
sudo docker compose up --build
```

- To stop the running container:

```
sudo docker compose stop
```

- To run the container:

```
sudo docker compose start
```

- To get log from already running container (after mounting the folder):

```
sudo docker compose logs --follow
```

#### Using Official Docker Commands

- Build Docker image:

```
sudo docker build . -t aeon-mltb
```

- Run the image:

```
sudo docker run --network host aeon-mltb
```

- To stop the running image:

```
sudo docker ps
```

```
sudo docker stop id
```

### 6. Open Required Ports:

1. Open all required ports using the shell script:

- Give execute permission & Run the script:

```
sudo chmod +x open_ports.sh
```

```
sudo ./open_ports.sh
```

2. Set `BASE_URL_PORT` and `RCLONE_SERVE_PORT` variables to any port you want to use. Default is `80` and `8080`
   respectively.

3. Check the number of processing units of your machine with `nproc` cmd and times it by 4, then
   edit `AsyncIOThreadsCount` in qBittorrent.conf or while bot working from bsetting->qbittorrent settings.

---

## Heroku CLI Deploy Guide (Windows, Linux, Android)

### Overview
This guide provides step-by-step instructions for deploying Aeon-MLTB to Heroku using the command line interface (CLI) across different platforms. This method deploys the **extended** branch directly to Heroku.

### Prerequisites
- Git installed on your system
- Heroku account
- GitHub account
- Basic terminal/command line knowledge

### Platform-Specific Setup

#### Windows
- Download and install Git from [https://git-scm.com/downloads](https://git-scm.com/downloads)
- Use Command Prompt (CMD) or PowerShell for terminal commands

#### Linux
Install Git using your distribution's package manager:
```bash
sudo apt update && sudo apt install git -y  # Ubuntu/Debian
sudo yum install git -y  # CentOS/RHEL
sudo pacman -S git  # Arch Linux
```

#### Android (Termux)
- Install Termux from [F-Droid](https://f-droid.org/packages/com.termux/)
- Update packages and install Git:
```bash
pkg update -y && pkg install git -y
```

### Step-by-Step Deployment Process

#### 1. Fork and Clone Repository

1. **Fork the Repository**
   - Go to [https://github.com/AeonOrg/Aeon-MLTB](https://github.com/AeonOrg/Aeon-MLTB)
   - Click the **Fork** button to create your own copy
   - Star the repository to show support

2. **Clone Your Fork and Switch to Extended Branch**
```bash
git clone https://github.com/YOUR-GITHUB-USERNAME/Aeon-MLTB.git && cd Aeon-MLTB && git checkout extended
```
Replace `YOUR-GITHUB-USERNAME` with your actual GitHub username.

#### 2. Prepare Deployment Branch

1. **Create Deploy Branch from Extended**
```bash
git checkout extended && git branch deploy && git checkout deploy
```

2. **Clean Up Files for Deployment**

   **Linux & Android (Termux):**
```bash
rm -rf bot myjd qBittorrent web sabnzbd sabnzbdapi && rm alive.py aria.sh
```

   **Windows:**
   - Manually delete the following folders: `bot`, `myjd`, `qBittorrent`, `web`, `sabnzbd`, `sabnzbdapi`
   - Manually delete the following files: `alive.py`, `aria.sh`

   **Keep only these files:**
   - `.git` folder
   - `Dockerfile`
   - `requirements.txt`
   - `config_sample.py`
   - `start.sh`
   - `update.py`

3. **Create Heroku Configuration File**
   Create a file named `heroku.yml` and add the following content:
```yaml
build:
  docker:
    web: Dockerfile
```

#### 3. Configure the Bot

1. **Rename Configuration File**
```bash
mv config_sample.py config.py  # Linux/Android
ren config_sample.py config.py  # Windows
```

2. **Fill Required Configurations**
   Edit `config.py` with your preferred text editor and fill in the necessary configurations:
   - `BOT_TOKEN` - Get from [@BotFather](https://t.me/BotFather)
   - `OWNER_ID` - Your Telegram User ID
   - `TELEGRAM_API` - Get from [my.telegram.org](https://my.telegram.org)
   - `TELEGRAM_HASH` - Get from [my.telegram.org](https://my.telegram.org)
   - `DATABASE_URL` - MongoDB connection string
   - Other optional configurations as needed

#### 4. Commit Changes

```bash
git add . -f && git commit -m "deploy: extended branch deployment"
```

#### 5. Install Heroku CLI

**Linux:**
```bash
sudo apt update -y && sudo apt install curl -y && curl https://cli-assets.heroku.com/install-ubuntu.sh | sh
```

**Windows (CMD/PowerShell):**
```cmd
curl https://cli-assets.heroku.com/install-ubuntu.sh | sh
```

**Android (Termux):**
```bash
pkg update -y && pkg upgrade -y && pkg install -y nodejs git && npm install -g heroku
```

#### 6. Login to Heroku

```bash
heroku login
```
- This will open a browser window for authentication
- If it doesn't open automatically, copy and paste the provided URL

#### 7. Create Heroku Application

**For Personal Account:**
```bash
heroku create your-app-name --region us  # US Region
heroku create your-app-name --region eu  # Europe Region
```

**For Team Account:**
```bash
heroku create your-app-name --team your-team-name --region us  # US Region
heroku create your-app-name --team your-team-name --region eu  # Europe Region
```

Replace `your-app-name` with your desired app name and `your-team-name` with your Heroku team name.

#### 8. Configure Git Remote and Set Container Stack

```bash
heroku git:remote -a YOUR-APP-NAME && heroku stack:set container
```
Replace `YOUR-APP-NAME` with the app name you created in step 7.

#### 9. Deploy Extended Branch to Heroku

```bash
git push heroku deploy:main -f
```

This command pushes your local `deploy` branch (which contains the extended branch code) to Heroku's `main` branch for deployment.

#### 10. Post-Deployment Setup

1. **Upload Important Files**
   After successful deployment, use the bot's settings to upload sensitive files:
   - Go to Bot Settings → Private Files
   - Upload files like:
     - `token.pickle` (Google Drive authentication)
     - `shorteners.txt` (URL shortener configurations)
     - `cookies.txt` (Browser cookies for yt-dlp)
     - `accounts.zip` (Service accounts for Google Drive)
     - `rclone.conf` (Rclone configuration)

2. **Configure Environment Variables (Optional)**
```bash
heroku config:set VARIABLE_NAME=value -a YOUR-APP-NAME
```

### Quick Command Summary

For experienced users, here's the complete deployment in one-liner commands:

```bash
# 1. Clone and setup
git clone https://github.com/YOUR-GITHUB-USERNAME/Aeon-MLTB.git && cd Aeon-MLTB && git checkout extended && git branch deploy && git checkout deploy

# 2. Clean files (Linux/Android)
rm -rf bot myjd qBittorrent web sabnzbd sabnzbdapi minim venv downloads dev docs && rm alive.py aria.sh default.otf docker-compose.yml open_ports.sh pyproject.toml streamrip_config.toml log.txt README.md

# 3. Create heroku.yml (Linux/Android)
echo -e "build:\n  docker:\n    web: Dockerfile" > heroku.yml

# 4. Configure and commit
mv config_sample.py config.py && git add . -f && git commit -m "deploy: extended branch deployment"

# 5. Install Heroku CLI (Linux)
sudo apt update -y && sudo apt install curl -y && curl https://cli-assets.heroku.com/install-ubuntu.sh | sh

# 6. Deploy to Heroku
heroku login && heroku create your-app-name --region us && heroku git:remote -a YOUR-APP-NAME && heroku stack:set container && git push heroku deploy:main -f
```

### Workflow Summary

```mermaid
graph TD
    A[Fork Repository] --> B[Clone Fork to Extended Branch]
    B --> C[Create Deploy Branch from Extended]
    C --> D[Clean Up Files]
    D --> E[Create heroku.yml]
    E --> F[Configure config.py]
    F --> G[Commit Changes]
    G --> H[Install Heroku CLI]
    H --> I[Login to Heroku]
    I --> J[Create Heroku App]
    J --> K[Add Git Remote & Set Container]
    K --> L[Deploy Deploy Branch (Extended Content) to Heroku]
    L --> M[Upload Private Files]
    M --> N[Bot Ready]
```

### Troubleshooting

#### Common Issues and Solutions

1. **Git Authentication Issues**
```bash
git config --global user.name "Your Name" && git config --global user.email "your.email@example.com"
```

2. **Heroku Login Problems**
   - Ensure you have a stable internet connection
   - Try using `heroku login -i` for interactive login
   - Clear browser cache if web login fails

3. **Deployment Failures**
```bash
heroku logs --tail -a YOUR-APP-NAME  # Check logs
```
   - Ensure all required files are present
   - Verify `heroku.yml` syntax is correct

4. **App Name Already Taken**
   - Choose a unique app name
   - Add random numbers or your username to make it unique

5. **Build Failures**
   - Check if `Dockerfile` is present and valid
   - Ensure `requirements.txt` contains all necessary dependencies
   - Verify container stack is set correctly

### Video Guides

- **Android Guide**: [Telegram Link](https://t.me/AeonDiscussion/80629)
- **Linux Guide**: [Telegram Link](https://t.me/AeonDiscussion/80729)

### Important Notes

- This method deploys the **extended** branch directly without merging to main
- Keep your fork updated by regularly syncing with the upstream repository
- Never commit sensitive information like tokens directly to the repository
- Use environment variables or the bot's private file upload feature for sensitive data
- The deployment process may take 5-15 minutes depending on your internet connection and Heroku's build time

### Updating Your Deployment

To update your deployed bot with the latest changes:

1. **Sync with upstream extended branch:**
```bash
git checkout extended && git pull upstream extended && git push origin extended
```

2. **Update deploy branch:**
```bash
git checkout deploy && git reset --hard extended && git push heroku deploy:main -f
```

---

## Aeon-MLTB Docker Build Guide

### Usage

1. **Run the Workflow**  
   - Go to the **Actions** tab in your repository.
   - Select **Docker.io** workflow.
   - Click **Run workflow** and provide:
     - **Docker Hub Username**
     - **Docker Hub Password**
     - **Docker Image Name**

2. **Result**  
   Your Docker image will be available at:  
   `docker.io/<username>/<image_name>:latest`.

### Inputs

| Input        | Description                        |
|--------------|------------------------------------|
| `username`   | Your Docker Hub username           |
| `password`   | Your Docker Hub password           |
| `image_name` | Name of the Docker image to build  |

### Notes

- **Platforms**: Builds for `linux/amd64` and `linux/arm64`.
- **Authentication**: Credentials are securely handled via inputs.

---