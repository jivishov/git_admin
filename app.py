import streamlit as st
from streamlit_ace import st_ace
from github import Github, GithubException
import base64
import os
from cryptography.fernet import Fernet
import anthropic
import time
from openai import OpenAI

st.set_page_config(page_title="GitHub Repository Manager", layout="wide")

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
@st.fragment
def list_repos(g):
    user = g.get_user()
    repos = user.get_repos()
    return [""] + [repo.name for repo in repos]

@st.fragment
def list_files(g, repo_name):
    if not repo_name:
        return []
    repo = g.get_user().get_repo(repo_name)
    contents = repo.get_contents("")
    return [content.path for content in contents if content.type == "file"]

@st.fragment
def get_file_content(g, repo_name, file_path):
    repo = g.get_user().get_repo(repo_name)
    content = repo.get_contents(file_path)
    return base64.b64decode(content.content).decode()

@st.fragment
def update_file(g, repo_name, file_path, content, commit_message):
    try:
        repo = g.get_user().get_repo(repo_name)
        contents = repo.get_contents(file_path)
        repo.update_file(contents.path, commit_message, content, contents.sha)
        st.success(f"File '{file_path}' updated successfully.")
        return True
    except Exception as e:
        st.error(f"Error updating file '{file_path}': {str(e)}")
        return False

@st.fragment
def create_repo(g, repo_name):
    try:
        user = g.get_user()
        user.create_repo(repo_name)
        st.success(f"Repository '{repo_name}' created successfully.")
    except Exception as e:
        st.error(f"Error creating repository: {str(e)}")

@st.fragment
def delete_repo(g, repo_name):
    try:
        repo = g.get_user().get_repo(repo_name)
        repo.delete()
        st.success(f"Repository '{repo_name}' deleted successfully.")
    except Exception as e:
        st.error(f"Error deleting repository: {str(e)}")

@st.dialog("Create/Delete Repositories")
def repo_management_dialog():
    repo_action = st.radio("Choose an action:", ["Create Repository", "Delete Repository"])
    repo_name = st.text_input("Repository Name:")

    if st.button("Submit"):
        g = st.session_state.g
        if repo_action == "Create Repository":
            create_repo(g, repo_name)
        elif repo_action == "Delete Repository":
            delete_repo(g, repo_name)

@st.fragment
def create_file(g, repo_name, file_path, content, commit_message):
    try:
        repo = g.get_user().get_repo(repo_name)
        repo.create_file(file_path, commit_message, content)
        st.success(f"File '{file_path}' created successfully in '{repo_name}'.")
    except Exception as e:
        st.error(f"Error creating file: {str(e)}")

@st.fragment
def delete_file(g, repo_name, file_path, commit_message):
    try:
        repo = g.get_user().get_repo(repo_name)
        contents = repo.get_contents(file_path)
        repo.delete_file(contents.path, commit_message, contents.sha)
        st.success(f"File '{file_path}' deleted successfully from '{repo_name}'.")
    except Exception as e:
        st.error(f"Error deleting file: {str(e)}")

@st.dialog("Create/Delete Files in Repo")
def file_management_dialog():
    repos = list_repos(st.session_state.g)
    selected_repo = st.selectbox("Choose a repository:", repos)
    
    file_action = st.radio("Choose an action:", ["Create File", "Delete File"])
    file_path = st.text_input("File Path:")
    content = st.text_area("File Content:", height=150)
    commit_message = st.text_input("Commit Message:")
    
    if st.button("Submit"):
        g = st.session_state.g
        if file_action == "Create File":
            create_file(g, selected_repo, file_path, content, commit_message)
        elif file_action == "Delete File":
            delete_file(g, selected_repo, file_path, commit_message)

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
@st.fragment
def generate_code_with_llm(prompt, app_code):
    selected_llm = st.session_state.get('selected_llm', 'Sonnet-3.5')

    if selected_llm == 'Sonnet-3.5':
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
            system="You are an expert Python programmer. Respond only with Python code that addresses the user's request, without any additional explanations. By default output full code unless specified by the user prompt.",
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
    elif selected_llm == 'GPT-4o':
        openai_api_key = st.secrets["OPENAI_API_KEY"]

        if not openai_api_key:
            st.error("OpenAI API key not found in secrets.")
            return None

        client = OpenAI(api_key=openai_api_key)
        completion = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are an expert Python programmer. Respond only with Python code that addresses the user's request, without any additional explanations. By default output full code unless specified by the user prompt."},
                {"role": "user", "content": prompt + " " + app_code}
            ]
        )
        return completion.choices[0].message.content

@st.dialog("Choose file from a repo")
def file_selector_dialog():
    repos = list_repos(st.session_state.g)
    selected_repo = st.selectbox("Choose a repository:", repos)
    
    files = []
    if selected_repo:
        files = list_files(st.session_state.g, selected_repo)
    
    selected_file = st.selectbox("Select File to Edit:", files)
    
    if st.button("Load File Content"):
        if selected_repo and selected_file:
            content = get_file_content(st.session_state.g, selected_repo, selected_file)
            st.session_state.file_content = content
            st.session_state.selected_repo = selected_repo
            st.session_state.selected_file = selected_file
            st.rerun()

@st.fragment
def code_editor_and_prompt():
    if 'file_content' not in st.session_state:
        st.session_state.file_content = ""
    
    col1, col2 = st.columns([3, 1])
    
    with col1:
        content = st_ace(
            value=st.session_state.file_content,
            language="python",
            theme="dreamweaver",
            keybinding="vscode",
            font_size=12,
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
                    st.error("Failed to generate code. Please check your API key.")

@st.dialog("Confirm repo file update")
def dialog_update(commit_message):
    st.write(f"**Confirm updating {st.session_state.selected_file}**")
    if st.button("I do"):
        if all(key in st.session_state for key in ['g', 'selected_repo', 'selected_file', 'file_content']):
            st.write("***Attempting to update the file...***")
            try:
                repo = st.session_state.g.get_user().get_repo(st.session_state.selected_repo)
                contents = repo.get_contents(st.session_state.selected_file)
                repo.update_file(contents.path, commit_message, st.session_state.file_content, contents.sha)
                st.success(f"File '{st.session_state.selected_file}' updated successfully. This message will stay for 7 seconds.")
                time.sleep(7)
                st.rerun()
            except Exception as e:
                st.error(f"Error updating file: {str(e)}")
        else:
            st.error("Missing required information to save changes. Message will stay for 7 seconds.")
            time.sleep(7)
            st.rerun()

@st.fragment
def save_changes():
    commit_message = st.text_input("Commit Message:", key='commit_message_txt')
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
            
            with st.sidebar:
                st.session_state.selected_llm = st.selectbox("Choose LLM:", ["Sonnet-3.5", "GPT-4o"])
                
                if st.button("Choose file from a repo"):
                    file_selector_dialog()
                
                st.divider()
                
                if st.button("Create/Delete Repositories"):
                    repo_management_dialog()
                
                st.divider()

                if st.button("Create/Delete Files in Repo"):
                    file_management_dialog()
                
                st.divider()
                
                if st.button("Logout"):
                    st.session_state.authenticated = False
                    st.session_state.github_token = ''
                    if 'g' in st.session_state:
                        del st.session_state.g
                    st.rerun()
            
            tab1, tab2 = st.tabs(["Main", "Sandbox"])
            
            with tab1:
                if 'selected_file' in st.session_state:
                    st.write(f"***Current repository/file***: {st.session_state.selected_repo} / {st.session_state.selected_file}")
                    code_editor_and_prompt()
                    save_changes()
            
            with tab2:
                if st.button("Run the code"):
                    code = st.session_state.file_content
                    code = code.replace("import streamlit as st", "")
                    try:
                        exec(code)
                    except Exception as e:
                        st.error(f"Error executing code: {str(e)}")

        except GithubException as e:
            st.error(f"An error occurred: {str(e)}")
            st.session_state.authenticated = False
            if 'g' in st.session_state:
                del st.session_state.g
            st.rerun()

if __name__ == "__main__":
    main()

# CSS to style the app
st.markdown("""
<style>
    .stApp {
        background-color: #f0f0f0;
        color: #333333;
    }
    .stTextInput > div > div > input {
        background-color: #ffffff;
        color: #333333;
        border: 1px solid #cccccc;
    }
    .stTextArea > div > div > textarea {
        background-color: #ffffff;
        color: #333333;
        border: 1px solid #cccccc;
    }
    .stSelectbox > div > div > select {
        background-color: #ffffff;
        color: #333333;
        border: 1px solid #cccccc;
    }
    .stButton > button {
        background-color: #4CAF50;
        color: white;
    }
    .sidebar .sidebar-content {
        background-color: #e0e0e0;
    }
    .stLabel {
        color: #2196F3;
        font-weight: bold;
    }
    .stHeader {
        color: #1976D2;
    }
    .stAce {
        border: 1px solid #2196F3;
    }
    .streamlit-expanderHeader {
        background-color: #e0e0e0;
        color: #333333;
    }
    .stAlert {
        background-color: #ffffff;
        color: #333333;
        border: 1px solid #cccccc;
    }
</style>
""", unsafe_allow_html=True)
