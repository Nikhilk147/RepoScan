# RepoScan - GitHub Assistant

> **Unlock the power of your GitHub data with AI**

Transform how you interact with your code repositories. RepoScan is an intelligent repository analysis tool that leverages AI to generate insights, automate code reviews, and enable natural language interactions with your GitHub projects.

[![Live Demo](https://img.shields.io/badge/Hugging%20Face-Demo-yellow)](https://nikhilk14-github-assistant.hf.space)
[![GitHub](https://img.shields.io/badge/GitHub-Repository-blue)](https://github.com/Nikhilk147/RepoScan)

---

## Table of Contents

- [Features](#features)
- [Demo](#demo)
- [Technology Stack](#technology-stack)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [API Keys Setup](#api-keys-setup)
- [Usage](#usage)
- [Project Structure](#project-structure)
- [Contributing](#contributing)
- [License](#license)

---

## Features

- **Intelligent Repository Analysis** - Deep dive into your GitHub repositories with AI-powered insights
- **Natural Language Queries** - Chat with your repositories and get instant answers about your codebase
- **Secure GitHub Integration** - OAuth-based authentication for safe access to your repositories
- **Automated Code Reviews** - Generate comprehensive code analysis and review suggestions
- **Project Insights** - Understand code structure, dependencies, and patterns across your projects
- **Real-time Processing** - Fast analysis powered by modern AI models

---

## Demo

Try out RepoScan without installation:

**Launch Live Demo:** [https://nikhilk14-github-assistant.hf.space](https://nikhilk14-github-assistant.hf.space)

Simply connect your GitHub account and start exploring your repositories with AI assistance!

---

## Technology Stack

- **Frontend**: HTML, CSS, JavaScript
- **Backend**: Python (FastAPI)
- **AI/ML**: Hugging Face Transformers, Large Language Models
- **Authentication**: GitHub OAuth
- **Deployment**: Hugging Face Spaces
- **Version Control**: Git, GitHub API

---

## Prerequisites

Before you begin, ensure you have the following installed:

- **Python 3.8+** - [Download Python](https://www.python.org/downloads/)
- **Git** - [Download Git](https://git-scm.com/downloads/)
- **pip** - Python package installer (comes with Python)
- **GitHub Account** - For OAuth integration
- **Hugging Face Account** (optional) - For API access

---

## Installation

### 1. Clone the Repository

```bash
git clone https://github.com/Nikhilk147/RepoScan.git
cd RepoScan
```

### 2. Create Virtual Environment

```bash
# Create virtual environment
python -m venv venv

# Activate virtual environment
# On Windows:
venv\Scripts\activate

# On macOS/Linux:
source venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

---

## API Keys Setup

To run RepoScan locally, you'll need to configure the following API keys:

### Required API Keys

#### 1. **GitHub OAuth Application**

Create a GitHub OAuth App to enable authentication:

1. Go to [GitHub Developer Settings](https://github.com/settings/developers)
2. Click **"New OAuth App"**
3. Fill in the application details:
   - **Application name**: RepoScan (or your preferred name)
   - **Homepage URL**: `http://localhost:5000` (for local development)
   - **Authorization callback URL**: `http://localhost:5000/callback`
4. Click **"Register application"**
5. Copy the **Client ID** and generate a **Client Secret**

#### 2. **Hugging Face API Token** (Optional but Recommended)

For enhanced AI capabilities:

1. Sign up at [Hugging Face](https://huggingface.co/)
2. Go to [Access Tokens](https://huggingface.co/settings/tokens)
3. Click **"New token"**
4. Create a token with `read` permissions
5. Copy the generated token

---

### Configuration

Create a `.env` file in the root directory of the project:

```bash
# Create .env file
touch .env
```

Add the following environment variables to your `.env` file:

```env
# GitHub OAuth Configuration
GITHUB_CLIENT_ID=your_github_client_id_here
GITHUB_CLIENT_SECRET=your_github_client_secret_here
GITHUB_CALLBACK_URL=http://localhost:5000/callback

# Hugging Face Configuration (Optional)
HUGGINGFACE_API_TOKEN=your_huggingface_token_here

# Application Configuration
SECRET_KEY=your_secret_key_here
FLASK_ENV=development
DEBUG=True

# Port Configuration (optional)
PORT=5000
```


1. **Ensure your virtual environment is activated**

```bash
# On Windows:
venv\Scripts\activate

# On macOS/Linux:
source venv/bin/activate
```

2. **Start the application**

```bash
python app.py
# or
flask run
```

3. **Access the application**

Open your browser and navigate to:
```
http://localhost:5000
```

4. **Connect GitHub Account**

- Click on **"Connect with GitHub"**
- Authorize the application
- Start analyzing your repositories!

---

### Using the Application

1. **Connect Your Account**: Authenticate with GitHub OAuth
2. **Select Repository**: Choose a repository from your account
3. **Ask Questions**: Use natural language to query your codebase
4. **Get Insights**: Receive AI-powered analysis and recommendations

**Example Queries:**
- "What does this repository do?"
- "Summarize the main functionality"
- "What are the key dependencies?"
- "Find potential security issues"
- "Explain the project structure"

---

## Project Structure

```
RepoScan/
├── app.py                  # Main application file
├── requirements.txt        # Python dependencies
├── .env.example           # Example environment variables
├── .gitignore             # Git ignore file
│
├── static/                # Static files (CSS, JS, images)
│   ├── css/
│   ├── js/
│   └── images/
│
├── templates/             # HTML templates
│   ├── index.html
│   ├── dashboard.html
│   └── analysis.html
│
├── utils/                 # Utility functions
│   ├── github_api.py     # GitHub API integration
│   ├── ai_analysis.py    # AI/ML processing
│   └── helpers.py        # Helper functions
│
└── README.md             # This file
```

---

## Contributing

Contributions are welcome! Here's how you can help:

1. **Fork the repository**
2. **Create a feature branch**
   ```bash
   git checkout -b feature/AmazingFeature
   ```
3. **Commit your changes**
   ```bash
   git commit -m 'Add some AmazingFeature'
   ```
4. **Push to the branch**
   ```bash
   git push origin feature/AmazingFeature
   ```
5. **Open a Pull Request**

### Development Guidelines

- Follow PEP 8 style guide for Python code
- Add comments for complex logic
- Update documentation for new features
- Test your changes thoroughly before submitting

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## Acknowledgments

- **Hugging Face** - For providing the AI infrastructure and hosting
- **GitHub** - For the comprehensive API and OAuth system
- **Open Source Community** - For the amazing libraries and tools

---

## Contact

**Nikhil K** 

- GitHub: [@Nikhilk147](https://github.com/Nikhilk147)
- Project Link: [https://github.com/Nikhilk147/RepoScan](https://github.com/Nikhilk147/RepoScan)
- Live Demo: [https://nikhilk14-github-assistant.hf.space](https://nikhilk14-github-assistant.hf.space)

---

## Show Your Support

If you find this project helpful, please consider giving it a star on GitHub!

---

**Made with care by Nikhil K**
