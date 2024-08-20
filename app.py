import streamlit as st
from streamlit_ace import st_ace, KEYBINDINGS, LANGUAGES, THEMES
from github import Github, GithubException
import base64
import os
from cryptography.fernet import Fernet
import anthropic
import time
import traceback

st.set_page_config(page_title="GitHub Repository Manager", layout="wide")

# CSS to style the app
st.markdown("""
<style>
    .stApp {
        background-color: #1e1e1e;
        color: #d4d4d4;
    }
    .stTextInput > div > div > input {
        background-color: #2d2d2d;
        color: #d4d4d4;
    }
    .stTextArea > div > div > textarea {
        background-color: #2d2d2d;
        color: #d4d4d4;
    }
    .stSelectbox > div > div > select {
        background-color: #2d2d2d;
        color: #d4d4d4;
    }
    .stButton > button {
        background-color: #0e639c;
        color: white;
    }
    .sidebar .sidebar-content {
        background-color: #252526;
    }
</style>
""", unsafe_allow_html=True)

# Encryption and token management functions
def encrypt_token(token):
    key = Fernet.generate_key()
    fernet = Fernet(key)
    encrypted_token = fernet.encrypt(token.encode())
    return key, encrypted_token

def decrypt_token(key, encrypted_token):
    fernet = Fernet(key)
    return fernet.decrypt(encrypted_token).decode()

def save_token(token):
    key, encrypted_token = encrypt_token(token)
    with open('github_token.key', 'wb') as key_file:
        key_file.write(key)
    with open('github_token.enc', 'wb') as token_file:
        token_file.write(encrypted_token)

def load_token():
    if os.path.exists('github_token.key') and os.path.exists('github_token.enc'):
        with open('github_token.key', 'rb') as key_file:
            key = key_file.read()
        with open('github_token.enc', 'rb') as token_file:
            encrypted_token = token_file.read()
        return decrypt_token(key, encrypted_token)
    return None

# GitHub operations
@st.cache_data
def list_repos(g):
    user = g.get_user()
    repos = user.get_repos()
    return [""] + [repo.name for repo in repos]

@st.cache_data
def list_files(g, repo_name):
    if not repo_name:
        return []
    repo = g.get_user().get_repo(repo_name)
    contents = repo.get_contents("")
    return [content.path for content in contents if content.type == "file"]

@st.cache_data
def get_file_content(g, repo_name, file_path):
    repo = g.get_user().get_repo(repo_name)
    content = repo.get_contents(file_path)
    return base64.b64decode(content.content).decode()

def update_file(g, repo_name, file_path, content, commit_message):
    try:
        repo = g.get_user().get_repo(repo_name)
        contents = repo.get_contents(file_path)
        repo.update_file(contents.path, commit_message, content, contents.sha)
        st.success(f"File '{file_path}' updated successfully.")
        return True
    except Exception as e:
        st.error(f"Error updating file '{file_path}': {str(e)}")
        st.error(f"Traceback: {traceback.format_exc()}")
        return False

# Authentication function
def github_auth():
    st.sidebar.title("GitHub Authentication")

    github_token = st.secrets["GITHUB_TOKEN"]

    if github_token:
        try:
            g = Github(github_token)
            user = g.get_user()
            st.session_state.github_token = github_token
            st.session_state.authenticated = True
            st.sidebar.success(f"Authenticated as {user.login}")
            return g
        except GithubException:
            st.sidebar.error("Authentication failed. Please check your GitHub token in secrets.")
    else:
        st.sidebar.error("GitHub token not found in secrets.")
    return None

# LLM code generation
@st.cache_data
def generate_code_with_llm(prompt, app_code):
    anthropic_api_key = st.secrets["ANTHROPIC_API_KEY"]

    if not anthropic_api_key:
        st.error("Anthropic API key not found in secrets.")
        return None

    client = anthropic.Anthropic(api_key=anthropic_api_key)
    message = client.messages.create(
        model="claude-3-5-sonnet-20240620",
        max_tokens=8192,
        temperature=0,
        extra_headers={"anthropic-beta": "max-tokens-3-5-sonnet-2024-07-15"},
        system="You are an expert Python programmer. Respond only with Python code that addresses the user's request, without any additional explanations.",
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": prompt+" "+app_code
                    }
                ]
            }
        ]
    )
    return message.content[0].text

def file_selector_dialog():
    repos = list_repos(st.session_state.g)
    selected_repo = st.selectbox("Choose a repository:", repos)
    
    files = list_files(st.session_state.g, selected_repo)
    selected_file = st.selectbox("Select File to Edit:", files)
    
    if st.button("Load File Content"):
        if selected_repo and selected_file:
            content = get_file_content(st.session_state.g, selected_repo, selected_file)
            st.session_state.file_content = content
            st.session_state.selected_repo = selected_repo
            st.session_state.selected_file = selected_file
            st.rerun()

def code_editor_and_prompt():
    if 'file_content' not in st.session_state:
        st.session_state.file_content = ""
    
    col1, col2 = st.columns([3, 1])
    
    with col1:
        content = st_ace(
            value=st.session_state.file_content,
            language="python",
            theme="monokai",
            keybinding="vscode",
            font_size=14,
            tab_size=4,
            show_gutter=True,
            show_print_margin=False,
            wrap=False,
            auto_update=True,
            readonly=False,
            min_lines=30,
            key="ace_editor",
        )
        st.session_state.file_content = content
    
    with col2:
        prompt = st.text_area("Enter your prompt:", placeholder="Enter your prompt for code generation.", height=150)
        
        if st.button("Execute prompt"):
            with st.spinner("Executing your prompt..."):
                generated_code = generate_code_with_llm(prompt, st.session_state.file_content)
                if generated_code:
                    st.session_state.file_content = generated_code
                else:
                    st.error("Failed to generate code. Please check your Anthropic API key.")

def dialog_update(commit_message):
    st.write(f"**Confirm updating {st.session_state.selected_file}**")
    if st.button("Confirm"):
        if all(key in st.session_state for key in ['g', 'selected_repo', 'selected_file', 'file_content']):
            st.write("***Attempting to update the file...***")
            try:
                repo = st.session_state.g.get_user().get_repo(st.session_state.selected_repo)
                contents = repo.get_contents(st.session_state.selected_file)
                repo.update_file(contents.path, commit_message, st.session_state.file_content, contents.sha)
                st.success(f"File '{st.session_state.selected_file}' updated successfully.")
                time.sleep(3)
                st.rerun()
            except Exception as e:
                st.error(f"Error updating file: {str(e)}")
                st.error(f"Traceback: {traceback.format_exc()}")
        else:
            st.error("Missing required information to save changes.")
            time.sleep(3)
            st.rerun()

def save_changes():
    commit_message = st.text_input("Commit Message:")
    save_button = st.button(f"Save Changes to {st.session_state.get('selected_file', 'No file selected')}")
    
    if save_button:
        dialog_update(commit_message)

def main():
    if 'authenticated' not in st.session_state:
        st.session_state.authenticated = False

    if not st.session_state.authenticated:
        g = github_auth()
        if g:
            st.session_state.g = g
            st.session_state.authenticated = True
            st.rerun()

    if st.session_state.authenticated:
        try:
            st.sidebar.title("GitHub Repository Manager")
            
            if st.sidebar.button("Choose file from a repo"):
                file_selector_dialog()
            
            st.sidebar.divider()
            
            if st.sidebar.button("Logout"):
                st.session_state.authenticated = False
                st.session_state.github_token = ''
                if 'g' in st.session_state:
                    del st.session_state.g
                st.rerun()
            
            if 'selected_file' in st.session_state:
                st.write(f"***Current repository/file***: {st.session_state.selected_repo} / {st.session_state.selected_file}")
                code_editor_and_prompt()
                save_changes()

        except GithubException as e:
            st.error(f"An error occurred: {str(e)}")
            st.error(f"Traceback: {traceback.format_exc()}")
            st.session_state.authenticated = False
            if 'g' in st.session_state:
                del st.session_state.g
            st.rerun()

if __name__ == "__main__":
    main()