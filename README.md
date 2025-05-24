![](https://github.com/5hojib/5hojib/raw/main/images/Aeon-MLTB.gif)

---

# Aeon-MLTB Bot

Aeon-MLTB is a streamlined and feature-rich bot designed for efficient deployment and enhanced functionality.

---

## Features

- **Minimalistic and Optimized**: Simplified by removing unnecessary code for better performance.
- **Effortless Deployment**: Fully configured for quick and easy deployment to Heroku.
- **Enhanced Capabilities**: Integrates features from multiple sources to provide a versatile bot experience.

---

## Read these

[Deployment](https://github.com/AeonOrg/Aeon-MLTB/blob/beta/docs/DEPLOYMENT.md)
[Configuration](https://github.com/AeonOrg/Aeon-MLTB/blob/beta/docs/CONFIGURATIONS.md)
[Commands](https://github.com/AeonOrg/Aeon-MLTB/blob/beta/docs/COMMANDS.md)
[Features](https://github.com/AeonOrg/Aeon-MLTB/blob/beta/docs/FEATURES.md)
[Extras](https://github.com/AeonOrg/Aeon-MLTB/blob/beta/docs/EXTRAS.md)

---

## Deployment Instructions (VPS)

Follow these steps to deploy Aeon to VPS:

### 1. Star the Repository
- Give the repository a star to show your support.

### 2. Clone The Repository
- Clone the repository to your VPS.

```
git clone https://github.com/AeonOrg/Aeon-MLTB.git && cd Aeon-MLTB
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

## Contributing

We welcome contributions! Whether it's bug fixes, feature enhancements, or general improvements:
- **Report issues**: Open an issue for bugs or suggestions.
- **Submit pull requests**: Share your contributions with the community.

---

# Aeon-MLTB Docker Build Guide

## Usage

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

## Inputs

| Input        | Description                        |
|--------------|------------------------------------|
| `username`   | Your Docker Hub username           |
| `password`   | Your Docker Hub password           |
| `image_name` | Name of the Docker image to build  |

## Notes

- **Platforms**: Builds for `linux/amd64` and `linux/arm64`.
- **Authentication**: Credentials are securely handled via inputs.

## Support

For issues, join here https://t.me/AeonDiscussion.


## License

This project is licensed under the MIT License. Refer to the [LICENSE](LICENSE) file for details.

---

## Acknowledgements

- Special thanks to the original developers of the [Mirror-Leech-Telegram-Bot](https://github.com/anasty17/mirror-leech-telegram-bot).
- Gratitude to contributors from various repositories whose features have been integrated into Aeon.
