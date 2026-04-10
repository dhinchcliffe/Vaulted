#!/Users/dhinchcliffe/openclaw/vaulted/venv/bin/python3
"""
Vaulted - A minimal Obsidian vault viewer and editor
"""

import os
import json
import re
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime
from html.parser import HTMLParser
from flask import Flask, render_template, jsonify, request, send_from_directory

# Optional imports for web fetching
try:
    import markdownify
    MARKDOWNIFY_AVAILABLE = True
except ImportError:
    MARKDOWNIFY_AVAILABLE = False

try:
    import wikipedia
    WIKIPEDIA_AVAILABLE = True
except ImportError:
    WIKIPEDIA_AVAILABLE = False

app = Flask(__name__)

# Vault path - your Obsidian vault
VAULT_PATH = os.path.expanduser("~/Dropbox/Apps/remotely-save/DPH Research")

def get_file_tree(path, relative_to=None):
    """Build a tree structure of the vault directory.
    
    Directories are listed first (alphabetically), followed by files (alphabetically).
    """
    if relative_to is None:
        relative_to = path
    
    dirs = []
    files = []
    
    try:
        entries = os.listdir(path)
    except (OSError, PermissionError) as e:
        app.logger.warning(f"Could not list directory {path}: {e}")
        return []
    
    for entry in entries:
        if entry.startswith('.'):
            continue
            
        full_path = os.path.join(path, entry)
        rel_path = os.path.relpath(full_path, relative_to)
        
        try:
            if os.path.isdir(full_path):
                children = get_file_tree(full_path, relative_to)
                dirs.append({
                    'name': entry,
                    'path': rel_path,
                    'type': 'directory',
                    'children': children
                })
            elif entry.endswith('.md'):
                files.append({
                    'name': entry,
                    'path': rel_path,
                    'type': 'file'
                })
        except (OSError, PermissionError) as e:
            # Skip files that can't be accessed (sparse sync)
            app.logger.debug(f"Skipping {full_path}: {e}")
            continue
    
    # Sort directories and files alphabetically by name, then return dirs first
    dirs.sort(key=lambda x: x['name'].lower())
    files.sort(key=lambda x: x['name'].lower())
    
    return dirs + files

def find_first_markdown(path):
    """Find the first accessible markdown file in the vault."""
    try:
        for root, dirs, files in os.walk(path):
            # Skip hidden directories
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            for file in sorted(files):
                if file.endswith('.md'):
                    full_path = os.path.join(root, file)
                    # Verify file is accessible (not sparse)
                    try:
                        with open(full_path, 'rb') as f:
                            f.read(1)
                        return os.path.relpath(full_path, path)
                    except (OSError, IOError):
                        continue
    except Exception:
        pass
    return None

@app.route('/')
def index():
    """Main page."""
    return render_template('index.html')

@app.route('/api/tree')
def get_tree():
    """Get the vault directory tree."""
    tree = get_file_tree(VAULT_PATH)
    return jsonify(tree)

@app.route('/api/file')
def get_file():
    """Get the contents of a markdown file."""
    filepath = request.args.get('path', '')
    if not filepath:
        return jsonify({'error': 'No path provided'}), 400
    
    # Security: ensure the path stays within the vault
    full_path = os.path.normpath(os.path.join(VAULT_PATH, filepath))
    if not full_path.startswith(os.path.normpath(VAULT_PATH)):
        return jsonify({'error': 'Invalid path'}), 403
    
    try:
        # Check if file is accessible (not sparse)
        with open(full_path, 'r', encoding='utf-8') as f:
            content = f.read()
        return jsonify({'content': content, 'path': filepath})
    except FileNotFoundError:
        return jsonify({'error': 'File not found'}), 404
    except OSError as e:
        if e.errno == 11:  # EDEADLK - Resource deadlock avoided (sparse file)
            return jsonify({'error': 'File not downloaded yet. Please open in Finder to download.'}), 503
        return jsonify({'error': str(e)}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/file', methods=['POST'])
def save_file():
    """Save changes to a markdown file."""
    data = request.get_json()
    if not data or 'path' not in data or 'content' not in data:
        return jsonify({'error': 'Missing path or content'}), 400
    
    filepath = data['path']
    content = data['content']
    
    # Security: ensure the path stays within the vault
    full_path = os.path.normpath(os.path.join(VAULT_PATH, filepath))
    if not full_path.startswith(os.path.normpath(VAULT_PATH)):
        return jsonify({'error': 'Invalid path'}), 403
    
    # Ensure directory exists
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    
    try:
        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/first')
def get_first():
    """Get the first markdown file path."""
    first = find_first_markdown(VAULT_PATH)
    return jsonify({'path': first})

@app.route('/api/status')
def get_status():
    """Get vault status info."""
    try:
        total_files = 0
        accessible_files = 0
        for root, dirs, files in os.walk(VAULT_PATH):
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            for file in files:
                if file.endswith('.md'):
                    total_files += 1
                    try:
                        full_path = os.path.join(root, file)
                        # Try to read first byte to check if file is accessible
                        with open(full_path, 'rb') as f:
                            f.read(1)
                        accessible_files += 1
                    except (OSError, PermissionError, IOError):
                        pass
        
        return jsonify({
            'vault_path': VAULT_PATH,
            'total_markdown_files': total_files,
            'accessible_files': accessible_files,
            'sync_status': 'syncing' if accessible_files < total_files else 'synced'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

class HTMLToMarkdown(HTMLParser):
    """Simple HTML parser to extract text content for markdown conversion."""
    def __init__(self):
        super().__init__()
        self.text = []
        self.skip_tags = {'script', 'style', 'nav', 'header', 'footer', 'aside'}
        self.skip_depth = 0
        
    def handle_starttag(self, tag, attrs):
        if tag in self.skip_tags:
            self.skip_depth += 1
        elif tag in ['p', 'div', 'article', 'section']:
            if self.text and not self.text[-1].endswith('\n\n'):
                self.text.append('\n\n')
        elif tag in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
            if self.text and not self.text[-1].endswith('\n\n'):
                self.text.append('\n\n')
            level = int(tag[1])
            self.text.append('#' * level + ' ')
        elif tag == 'li':
            self.text.append('- ')
        elif tag == 'br':
            self.text.append('\n')
        elif tag == 'a':
            attrs_dict = dict(attrs)
            if 'href' in attrs_dict:
                self.current_href = attrs_dict['href']
        elif tag in ['b', 'strong']:
            self.text.append('**')
        elif tag in ['i', 'em']:
            self.text.append('*')
            
    def handle_endtag(self, tag):
        if tag in self.skip_tags:
            self.skip_depth -= 1
        elif tag in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
            self.text.append('\n\n')
        elif tag == 'p':
            self.text.append('\n\n')
        elif tag == 'a':
            if hasattr(self, 'current_href'):
                self.text.append(f']({self.current_href})')
                delattr(self, 'current_href')
        elif tag in ['b', 'strong']:
            self.text.append('**')
        elif tag in ['i', 'em']:
            self.text.append('*')
            
    def handle_data(self, data):
        if self.skip_depth == 0:
            # Clean up whitespace but preserve structure
            cleaned = ' '.join(data.split())
            if cleaned:
                self.text.append(cleaned)
                
    def get_markdown(self):
        result = ''.join(self.text)
        # Clean up excessive newlines
        result = re.sub(r'\n{3,}', '\n\n', result)
        return result.strip()


def fetch_wikipedia_page(url):
    """Fetch a Wikipedia page with images using MediaWiki API.
    
    Uses the parse API to get HTML content, then converts to Markdown
    preserving images and structure.
    """
    try:
        # Extract page title and language from URL
        # URL format: https://en.wikipedia.org/wiki/Page_Title
        match = re.search(r'wikipedia\.org/wiki/([^#?]+)', url)
        if not match:
            return {'error': 'Could not extract Wikipedia page title from URL'}
        
        page_title = urllib.parse.unquote(match.group(1))
        lang_match = re.search(r'https://([a-z]+)\.wikipedia\.org', url)
        lang = lang_match.group(1) if lang_match else 'en'
        
        # Build API URL
        api_url = f"https://{lang}.wikipedia.org/w/api.php"
        params = {
            'action': 'parse',
            'page': page_title,
            'prop': 'text|images|displaytitle',
            'format': 'json',
            'redirects': 'true'
        }
        
        # Fetch from API
        headers = {'User-Agent': 'Vaulted/1.0 (research tool)'}
        req = urllib.request.Request(
            api_url + '?' + urllib.parse.urlencode(params),
            headers=headers
        )
        
        with urllib.request.urlopen(req, timeout=30) as response:
            data = json.loads(response.read().decode('utf-8'))
        
        if 'error' in data:
            return {'error': f"Wikipedia API error: {data['error'].get('info', 'Unknown error')}"}
        
        parse_data = data['parse']
        title = re.sub(r'<[^>]+>', '', parse_data.get('displaytitle', parse_data['title']))
        html_content = parse_data['text']['*']
        images = parse_data.get('images', [])
        
        # Convert HTML to Markdown using markdownify
        if MARKDOWNIFY_AVAILABLE:
            # Clean up Wikipedia-specific elements before conversion
            # Remove edit links, navigation, etc.
            html_content = re.sub(r'<span class="mw-editsection[^"]*"[^>]*>.*?</span>', '', html_content, flags=re.DOTALL)
            html_content = re.sub(r'<div class="mw-parser-output">\s*<div class="hatnote[^"]*"[^>]*>.*?</div>', '', html_content, flags=re.DOTALL)

            # Extract infobox images before table conversion (markdownify strips images in tables)
            infobox_images = []
            for img_match in re.finditer(r'<td[^>]*class="[^"]*infobox-image[^"]*"[^>]*>.*?<img[^>]+src="([^"]+)"[^>]*>.*?</td>', html_content, re.DOTALL):
                img_url = img_match.group(1)
                if img_url.startswith('//'):
                    img_url = 'https:' + img_url
                infobox_images.append(f'<img src="{img_url}">')

            # Convert to markdown
            content = markdownify.markdownify(
                html_content,
                heading_style='ATX'
            )

            # Prepend extracted infobox images
            if infobox_images:
                content = '\n\n'.join(infobox_images) + '\n\n' + content
            
            # Clean up Wikipedia image URLs - convert relative to absolute
            content = re.sub(
                r'!\[([^\]]*)\]\(/wiki/File:([^)]+)\)',
                r'![\1](https://en.wikipedia.org/wiki/File:\2)',
                content
            )
            
            # Clean up excessive whitespace
            content = re.sub(r'\n{3,}', '\n\n', content)
            content = content.strip()
        else:
            # Fallback: extract plain text
            parser = HTMLToMarkdown()
            parser.feed(html_content)
            content = parser.get_markdown()
        
        # Add image list at the end if we have images
        if images:
            image_links = []
            for img in images[:10]:  # Limit to first 10 images
                if not img.startswith('File:OOjs'):  # Skip UI icons
                    img_name = img.replace('File:', '')
                    image_links.append(f"- [{img}](https://en.wikipedia.org/wiki/{img.replace(' ', '_')})")
            
            if image_links:
                content += "\n\n## Images on this page\n\n"
                content += "\n".join(image_links)
        
        return {
            'title': title,
            'content': content,
            'url': url
        }
        
    except urllib.error.HTTPError as e:
        return {'error': f'HTTP Error {e.code}: {e.reason}'}
    except Exception as e:
        return {'error': f'Failed to fetch Wikipedia page: {str(e)}'}


def fetch_web_page(url):
    """Fetch a web page and extract its content."""
    # Check if this is a Wikipedia URL
    if 'wikipedia.org/wiki/' in url and WIKIPEDIA_AVAILABLE:
        return fetch_wikipedia_page(url)
    
    # For non-Wikipedia pages, use markdownify if available
    if MARKDOWNIFY_AVAILABLE:
        return fetch_web_page_markdownify(url)
    
    # Fallback to legacy parser
    return fetch_web_page_legacy(url)


def extract_twitter_handle_and_id(url):
    """Extract Twitter/X handle and status ID from URL.
    
    Returns tuple (handle, status_id) or (None, None) if not a valid X/Twitter URL.
    """
    # Match patterns like:
    # https://x.com/username/status/123456...
    # https://twitter.com/username/status/123456...
    patterns = [
        r'(?:https?://)?(?:www\.)?(?:x\.com|twitter\.com)/([^/]+)/status/(\d+)',
        r'(?:https?://)?(?:www\.)?(?:x\.com|twitter\.com)/([^/]+)/status/(\d+)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url, re.IGNORECASE)
        if match:
            return match.group(1), match.group(2)
    
    return None, None


def fetch_x_post(url):
    """Handle X/Twitter URLs specially since they block standard requests.
    
    X.com requires JavaScript to render content, so we can't fetch the actual post text
    through standard HTTP requests. We try to extract metadata from the page's embedded
    JSON data, and fall back to a reference entry if that fails.
    """
    handle, status_id = extract_twitter_handle_and_id(url)
    
    if not handle or not status_id:
        return {'error': 'Could not parse X/Twitter URL'}
    
    # Try to fetch the page and extract metadata from __INITIAL_STATE__
    try:
        import requests
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
        }
        
        response = requests.get(url, headers=headers, timeout=30)
        html = response.text
        
        # Try to extract __INITIAL_STATE__ JSON
        match = re.search(r'window\.__INITIAL_STATE__\s*=\s*(\{.*?\});(?:window\.|</script>)', html, re.DOTALL)
        if match:
            data = json.loads(match.group(1))
            
            # Look for user info
            user_name = handle
            user_display_name = handle
            if 'entities' in data and 'users' in data['entities']:
                users = data['entities']['users'].get('entities', {})
                # Find user by screen_name
                for user_id, user in users.items():
                    if user.get('screen_name', '').lower() == handle.lower():
                        user_name = user.get('screen_name', handle)
                        user_display_name = user.get('name', handle)
                        break
            
            # Try to find tweet text in the HTML meta tags or JSON
            tweet_text = None
            
            # Check if there's any tweet content in the entities
            tweets = data.get('entities', {}).get('tweets', {}).get('entities', {})
            for tweet_id, tweet in tweets.items():
                if str(tweet_id) == str(status_id) or status_id in str(tweet_id):
                    tweet_text = tweet.get('full_text') or tweet.get('text')
                    break
            
            # If we found tweet text, use it
            if tweet_text:
                title = f"X Post by @{user_name}"
                content = f"""**@{user_name}** ({user_display_name})

{tweet_text}

---
**Post URL:** {url}
**Post ID:** {status_id}
*Note: Fetched from X.com metadata*
"""
                return {
                    'title': title,
                    'content': content,
                    'url': url,
                    'handle': user_name,
                    'status_id': status_id
                }
    except Exception:
        # If extraction fails, fall through to reference entry
        pass
    
    # Fall back to reference entry
    title = f"X Post by @{handle}"
    
    content = f"""**@{handle}**

This is an X (Twitter) post.

**Note:** X.com requires JavaScript to display content and blocks automated fetching. 
To view the full post content, please open the link below in your browser.

**Post URL:** {url}

**Post ID:** {status_id}
"""
    
    return {
        'title': title,
        'content': content,
        'url': url,
        'handle': handle,
        'status_id': status_id
    }


def fetch_web_page_markdownify(url):
    """Fetch web page using markdownify library."""
    # Check if this is an X/Twitter URL first
    if 'x.com' in url or 'twitter.com' in url:
        return fetch_x_post(url)
    
    try:
        import requests
        from bs4 import BeautifulSoup
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Get title
        title = 'Untitled'
        if soup.title:
            title = soup.title.get_text().strip()
        title = re.sub(r'[\\/:*?"<>|]', '', title)
        
        # Check if this is a JavaScript-required page (like X/Twitter error page)
        noscript = soup.find('noscript')
        if noscript and 'JavaScript' in str(noscript):
            # Check if it's specifically an X/Twitter block
            page_text = soup.get_text()
            if 'x.com' in page_text or 'twitter.com' in page_text:
                if 'JavaScript is not available' in page_text or 'JavaScript is disabled' in page_text:
                    # Try to extract handle from URL and create reference
                    handle, status_id = extract_twitter_handle_and_id(url)
                    if handle:
                        return fetch_x_post(url)
        
        # Try to find main content
        content_html = str(soup)
        
        # Look for article/main content first
        for selector in ['article', 'main', '[role="main"]', '.article', '.post', '.entry']:
            elem = soup.select_one(selector)
            if elem:
                content_html = str(elem)
                break
        
        # Convert to markdown
        content = markdownify.markdownify(content_html, heading_style='ATX', strip=['a'])
        
        # Clean up excessive whitespace
        content = re.sub(r'\n{3,}', '\n\n', content)
        
        return {
            'title': title,
            'content': content.strip(),
            'url': url
        }
        
    except Exception as e:
        # Fallback to legacy on error
        return fetch_web_page_legacy(url)


def fetch_web_page_legacy(url):
    """Fetch a web page and extract its content."""
    try:
        req = urllib.request.Request(
            url,
            headers={
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'identity',
            }
        )
        
        with urllib.request.urlopen(req, timeout=30) as response:
            html = response.read().decode('utf-8', errors='ignore')
            
        # Extract title
        title_match = re.search(r'<title[^>]*>(.*?)</title>', html, re.IGNORECASE | re.DOTALL)
        title = title_match.group(1).strip() if title_match else 'Untitled'
        # Clean up title for filename
        title = re.sub(r'[\\/:*?"<>|]', '', title)
        
        # Try to find main content area
        content_html = html
        
        # Look for common content containers
        content_patterns = [
            r'<article[^>]*>(.*?)</article>',
            r'<main[^>]*>(.*?)</main>',
            r'<div[^>]*class="[^"]*content[^"]*"[^>]*>(.*?)</div>',
            r'<div[^>]*class="[^"]*article[^"]*"[^>]*>(.*?)</div>',
            r'<div[^>]*id="[^"]*content[^"]*"[^>]*>(.*?)</div>',
            r'<div[^>]*id="[^"]*main[^"]*"[^>]*>(.*?)</div>',
        ]
        
        for pattern in content_patterns:
            match = re.search(pattern, html, re.IGNORECASE | re.DOTALL)
            if match:
                content_html = match.group(1)
                break
        
        # Parse HTML to markdown
        parser = HTMLToMarkdown()
        parser.feed(content_html)
        content = parser.get_markdown()
        
        return {
            'title': title,
            'content': content,
            'url': url
        }
        
    except urllib.error.HTTPError as e:
        return {'error': f'HTTP Error {e.code}: {e.reason}'}
    except urllib.error.URLError as e:
        return {'error': f'URL Error: {e.reason}'}
    except Exception as e:
        return {'error': f'Failed to fetch page: {str(e)}'}


@app.route('/api/fetch-web', methods=['POST'])
def fetch_web():
    """Fetch a web page and save it to ReadItLater inbox."""
    data = request.get_json()
    if not data or 'url' not in data:
        return jsonify({'error': 'No URL provided'}), 400
    
    url = data['url'].strip()
    if not url:
        return jsonify({'error': 'Empty URL'}), 400
    
    # Add https:// if no protocol specified
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    
    # Fetch the page
    result = fetch_web_page(url)
    
    if 'error' in result:
        return jsonify({'error': result['error']}), 500
    
    # Generate filename (title first, then date for easy scanning)
    date_str = datetime.now().strftime('%Y-%m-%d')
    safe_title = result['title'][:80] if result['title'] else 'untitled'
    safe_title = re.sub(r'\s+', ' ', safe_title).strip()
    filename = f"{safe_title} - {date_str}.md"
    
    # ReadItLater inbox path
    inbox_path = os.path.join(VAULT_PATH, 'ReadItLater Inbox', filename)
    
    # Ensure directory exists
    os.makedirs(os.path.dirname(inbox_path), exist_ok=True)
    
    # Check if file exists and append number if needed
    counter = 1
    original_inbox_path = inbox_path
    while os.path.exists(inbox_path):
        name, ext = os.path.splitext(original_inbox_path)
        inbox_path = f"{name} ({counter}){ext}"
        counter += 1
    
    # Create markdown content with YAML frontmatter for source URL
    markdown_content = f"""---
source_url: {result['url']}
---

[[ReadItLater]] [[Article]]

# [{result['title']}]({result['url']})

{result['content']}

---
*Saved from {result['url']} on {datetime.now().strftime('%Y-%m-%d %H:%M')}*
"""
    
    try:
        with open(inbox_path, 'w', encoding='utf-8') as f:
            f.write(markdown_content)
        
        rel_path = os.path.relpath(inbox_path, VAULT_PATH)
        return jsonify({
            'success': True,
            'path': rel_path,
            'title': result['title']
        })
    except Exception as e:
        return jsonify({'error': f'Failed to save file: {str(e)}'}), 500


@app.route('/api/attachment/<path:filepath>')
def get_attachment(filepath):
    """Serve image attachments from the vault.
    
    Tries multiple locations in order:
    1. Explicit path (if filepath contains /)
    2. Current file directory (if context provided via from param)
    3. Vault root
    """
    # Security: ensure the path stays within the vault
    def is_safe(path):
        return os.path.normpath(path).startswith(os.path.normpath(VAULT_PATH))
    
    # Get the referring file context (for local folder resolution)
    from_file = request.args.get('from', '')
    
    # Build list of paths to try
    paths_to_try = []
    
    # 1. If path has explicit directory, try it as-is first
    if '/' in filepath:
        paths_to_try.append(os.path.join(VAULT_PATH, filepath))
    
    # 2. Try relative to the current file's directory
    if from_file and '/' in from_file:
        current_dir = os.path.dirname(os.path.join(VAULT_PATH, from_file))
        paths_to_try.append(os.path.join(current_dir, filepath))
    
    # 3. Try vault root (always try this)
    paths_to_try.append(os.path.join(VAULT_PATH, filepath))
    
    # Try each path in order
    for full_path in paths_to_try:
        if not is_safe(full_path):
            continue
        if os.path.isfile(full_path):
            directory = os.path.dirname(full_path)
            filename = os.path.basename(full_path)
            try:
                return send_from_directory(directory, filename)
            except Exception:
                continue
    
    # None found
    return jsonify({'error': 'File not found'}), 404


def compress_tree_for_ai(path, relative_to=None, level=0):
    """Build a compressed tree structure for AI context.
    
    Returns folder structure with file counts instead of full file lists.
    Limits depth to avoid token explosion.
    """
    if relative_to is None:
        relative_to = path
    
    if level > 5:  # Limit depth to 5 levels
        return []
    
    result = []
    
    try:
        entries = os.listdir(path)
    except (OSError, PermissionError):
        return []
    
    dirs = []
    files = []
    
    for entry in entries:
        if entry.startswith('.'):
            continue
        full_path = os.path.join(path, entry)
        rel_path = os.path.relpath(full_path, relative_to)
        try:
            if os.path.isdir(full_path):
                dirs.append((entry, rel_path, full_path))
            elif entry.endswith('.md'):
                files.append(entry)
        except (OSError, PermissionError):
            continue
    
    # Add directories with their compressed children
    for name, rel_path, full_path in sorted(dirs, key=lambda x: x[0].lower()):
        children = compress_tree_for_ai(full_path, relative_to, level + 1)
        dir_info = {'name': name, 'type': 'directory', 'children': children}
        
        # Count files in this directory (not recursive)
        try:
            file_count = len([f for f in os.listdir(full_path) 
                           if f.endswith('.md') and not f.startswith('.')])
            if file_count > 0:
                dir_info['file_count'] = file_count
        except:
            pass
        
        result.append(dir_info)
    
    # Only include files if at root level or if there aren't too many
    if level == 0 or len(files) <= 5:
        for name in sorted(files, key=str.lower):
            result.append({'name': name, 'type': 'file'})
    else:
        # Just show count if too many files
        if files:
            result.append({'name': f'[{len(files)} files]', 'type': 'file_count'})
    
    return result


def tree_to_text(tree, indent=0):
    """Convert compressed tree to text format for AI prompt."""
    lines = []
    prefix = '  ' * indent
    
    for item in tree:
        if item['type'] == 'directory':
            count_str = f" ({item.get('file_count', 0)} files)" if 'file_count' in item else ''
            lines.append(f"{prefix}{item['name']}/{count_str}")
            if item.get('children'):
                lines.extend(tree_to_text(item['children'], indent + 1))
        elif item['type'] == 'file':
            lines.append(f"{prefix}- {item['name']}")
        elif item['type'] == 'file_count':
            lines.append(f"{prefix}{item['name']}")
    
    return lines


@app.route('/api/suggest-file-location', methods=['POST'])
def suggest_file_location():
    """Use AI to suggest where to file the current document.
    
    Expects JSON: {path: "file/path.md", content: "markdown content"}
    Returns: {suggestion: "Folder/Path", reasoning: "explanation"}
    """
    data = request.get_json()
    if not data or 'path' not in data:
        return jsonify({'error': 'No file path provided'}), 400
    
    filepath = data['path']
    content = data.get('content', '')
    
    # Security check
    full_path = os.path.normpath(os.path.join(VAULT_PATH, filepath))
    if not full_path.startswith(os.path.normpath(VAULT_PATH)):
        return jsonify({'error': 'Invalid path'}), 403
    
    # If content not provided, read from file
    if not content:
        try:
            with open(full_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            return jsonify({'error': f'Could not read file: {str(e)}'}), 500
    
    # Get compressed tree structure
    tree = compress_tree_for_ai(VAULT_PATH)
    tree_text = '\n'.join(tree_to_text(tree))
    
    # Truncate content to first 800 chars (approx 200 tokens)
    content_preview = content[:800].strip()
    if len(content) > 800:
        content_preview += '\n...'
    
    # Build prompt for AI
    prompt = f"""You are organizing a knowledge vault. Given the vault structure and a document, suggest the best folder to file it in.

VAULT STRUCTURE:
{tree_text}

DOCUMENT (first ~800 chars):
{content_preview}

Based on the document's content and the existing vault structure, suggest the best folder path to file this document.

IMPORTANT:
- Prefer existing folders when there's a clear topical match
- If no existing folder fits well, suggest creating a NEW category that matches the document's subject (e.g., "Geography", "History", "Technology", etc.)
- Only suggest "ReadItLater Inbox" as a last resort for uncategorized content
- HISTORY RULE: Content about events/people/civilizations before 1500 AD should go under "Personal Research/Ancient History" (create this path if it doesn't exist)
- Be liberal in accepting existing folders — avoid creating overly specific new folders when a broader existing one works
- When multiple existing folders could fit, prefer the MORE SPECIFIC/DEEPER path (e.g., "Personal Research/Sailing" over just "Sailing")

Respond in this exact format:
SUGGESTION: Folder/Subfolder
REASONING: Brief explanation of why this location fits"""
    
    try:
        # Use OpenAI API with gpt-4o-mini for cost efficiency
        import openai
        
        # Get API key from environment
        api_key = os.environ.get('OPENAI_API_KEY')
        if not api_key:
            # Try to load from .env file
            env_path = os.path.expanduser('~/.openclaw/.env')
            if os.path.exists(env_path):
                with open(env_path, 'r') as f:
                    for line in f:
                        if line.startswith('OPENAI_API_KEY='):
                            api_key = line.strip().split('=', 1)[1].strip().strip('"').strip("'")
                            break
        
        if not api_key:
            return jsonify({'error': 'OpenAI API key not configured'}), 500
        
        client = openai.OpenAI(api_key=api_key)
        
        response = client.chat.completions.create(
            model='gpt-4o-mini',
            messages=[
                {'role': 'system', 'content': 'You are a helpful assistant that organizes documents into a knowledge vault. Be concise.'},
                {'role': 'user', 'content': prompt}
            ],
            temperature=0.3,
            max_completion_tokens=150
        )
        
        ai_response = response.choices[0].message.content.strip()
        
        # Parse response
        suggestion = None
        reasoning = None
        
        for line in ai_response.split('\n'):
            if line.startswith('SUGGESTION:'):
                suggestion = line.replace('SUGGESTION:', '').strip()
            elif line.startswith('REASONING:'):
                reasoning = line.replace('REASONING:', '').strip()
        
        # Fallback parsing
        if not suggestion:
            lines = [l.strip() for l in ai_response.split('\n') if l.strip()]
            if lines:
                suggestion = lines[0]
        if not reasoning:
            reasoning = 'Based on document content analysis'
        
        return jsonify({
            'suggestion': suggestion,
            'reasoning': reasoning,
            'tree_preview': tree_text[:500]  # For debugging
        })
        
    except Exception as e:
        app.logger.error(f'AI suggestion failed: {e}')
        return jsonify({'error': f'AI suggestion failed: {str(e)}'}), 500


@app.route('/api/move-file', methods=['POST'])
def move_file():
    """Move a file to a new location within the vault.

    Expects JSON: {from_path: "old/path.md", to_folder: "New/Folder"}
    Returns: {success: true, new_path: "New/Folder/filename.md"}
    """
    data = request.get_json()
    if not data or 'from_path' not in data or 'to_folder' not in data:
        return jsonify({'error': 'Missing from_path or to_folder'}), 400

    from_path = data['from_path']
    to_folder = data['to_folder'].lstrip('/')

    # Security checks
    from_full = os.path.normpath(os.path.join(VAULT_PATH, from_path))
    if not from_full.startswith(os.path.normpath(VAULT_PATH)):
        return jsonify({'error': 'Invalid from_path'}), 403

    to_folder_full = os.path.normpath(os.path.join(VAULT_PATH, to_folder))
    if not to_folder_full.startswith(os.path.normpath(VAULT_PATH)):
        return jsonify({'error': 'Invalid to_folder'}), 403

    # Get filename
    filename = os.path.basename(from_path)

    # Build destination path
    new_full_path = os.path.join(to_folder_full, filename)
    new_rel_path = os.path.relpath(new_full_path, VAULT_PATH)

    # Check if destination already exists
    if os.path.exists(new_full_path):
        # Append number to filename
        name, ext = os.path.splitext(filename)
        counter = 1
        while os.path.exists(new_full_path):
            new_filename = f"{name} ({counter}){ext}"
            new_full_path = os.path.join(to_folder_full, new_filename)
            new_rel_path = os.path.relpath(new_full_path, VAULT_PATH)
            counter += 1

    try:
        # Ensure destination directory exists
        os.makedirs(to_folder_full, exist_ok=True)

        # Move the file
        import shutil
        shutil.move(from_full, new_full_path)

        return jsonify({
            'success': True,
            'new_path': new_rel_path,
            'filename': os.path.basename(new_full_path)
        })
    except Exception as e:
        return jsonify({'error': f'Failed to move file: {str(e)}'}), 500


@app.route('/api/create-page', methods=['POST'])
def create_page():
    """Create a new blank markdown page in a folder.

    Expects JSON: {folder: "Folder/Path", filename: "page name.md"}
    Returns: {success: true, path: "Folder/Path/page name.md"}
    """
    data = request.get_json()
    if not data or 'folder' not in data or 'filename' not in data:
        return jsonify({'error': 'Missing folder or filename'}), 400

    folder = data['folder'].lstrip('/')
    filename = data['filename'].lstrip('/')

    # Security checks
    folder_full = os.path.normpath(os.path.join(VAULT_PATH, folder))
    if not folder_full.startswith(os.path.normpath(VAULT_PATH)):
        return jsonify({'error': 'Invalid folder path'}), 403

    # Ensure filename ends with .md
    if not filename.endswith('.md'):
        filename += '.md'

    # Security check on filename (no path traversal)
    if '/' in filename or '\\' in filename or '..' in filename:
        return jsonify({'error': 'Filename cannot contain path separators'}), 400

    # Build full path
    full_path = os.path.join(folder_full, filename)

    # Security check on final path
    if not full_path.startswith(os.path.normpath(VAULT_PATH)):
        return jsonify({'error': 'Invalid path'}), 403

    # Check if file already exists
    if os.path.exists(full_path):
        return jsonify({'error': 'A file with that name already exists'}), 409

    try:
        # Ensure directory exists
        os.makedirs(folder_full, exist_ok=True)

        # Create blank markdown file with minimal frontmatter
        date_str = datetime.now().strftime('%Y-%m-%d')
        content = f"""---
created: {date_str}
---

# {filename.replace('.md', '')}

"""
        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(content)

        rel_path = os.path.relpath(full_path, VAULT_PATH)
        return jsonify({
            'success': True,
            'path': rel_path,
            'filename': filename
        })
    except Exception as e:
        return jsonify({'error': f'Failed to create page: {str(e)}'}), 500


@app.route('/api/rename', methods=['POST'])
def rename_item():
    """Rename a file or directory within the vault.

    Expects JSON: {path: "old/path.md", new_name: "newname.md"}
    Returns: {success: true, new_path: "old/newname.md"}
    """
    data = request.get_json()
    if not data or 'path' not in data or 'new_name' not in data:
        return jsonify({'error': 'Missing path or new_name'}), 400

    path = data['path']
    new_name = data['new_name'].lstrip('/')

    # Security checks
    full_path = os.path.normpath(os.path.join(VAULT_PATH, path))
    if not full_path.startswith(os.path.normpath(VAULT_PATH)):
        return jsonify({'error': 'Invalid path'}), 403

    # Check for path traversal in new_name
    if '/' in new_name or '\\' in new_name or '..' in new_name:
        return jsonify({'error': 'New name cannot contain path separators'}), 400

    # Build new path (same parent directory)
    parent_dir = os.path.dirname(full_path)
    new_full_path = os.path.join(parent_dir, new_name)
    new_rel_path = os.path.relpath(new_full_path, VAULT_PATH)

    # Security check on new path
    if not new_full_path.startswith(os.path.normpath(VAULT_PATH)):
        return jsonify({'error': 'Invalid new name'}), 403

    # Check if source exists
    if not os.path.exists(full_path):
        return jsonify({'error': 'Source does not exist'}), 404

    # Check if destination already exists
    if os.path.exists(new_full_path):
        return jsonify({'error': 'A file or folder with that name already exists'}), 409

    try:
        import shutil
        shutil.move(full_path, new_full_path)

        return jsonify({
            'success': True,
            'new_path': new_rel_path,
            'new_name': new_name
        })
    except Exception as e:
        return jsonify({'error': f'Failed to rename: {str(e)}'}), 500


@app.route('/api/restart', methods=['POST'])
def restart_server():
    """Graceful restart - terminates this process.
    
    When running under LaunchAgent, the agent will automatically restart
    the process within 10 seconds, loading the latest code.
    
    Supported Apps:
    - Vaulted (port 5006) ✓
    
    Planned:
    - OpenClaw Tasks (port 5004)
    - Siri API (port 5005)
    """
    import signal
    import threading
    
    def delayed_shutdown():
        import time
        time.sleep(0.5)  # Give response time to send
        os.kill(os.getpid(), signal.SIGTERM)
    
    # Start shutdown in background thread
    threading.Thread(target=delayed_shutdown, daemon=True).start()
    
    return jsonify({
        'status': 'restarting',
        'message': 'Server shutting down. LaunchAgent will restart within 10 seconds.',
        'pid': os.getpid()
    })


if __name__ == '__main__':
    print(f"Vaulted starting...")
    print(f"Vault path: {VAULT_PATH}")
    print(f"Open http://localhost:5006 in your browser")
    # Note: debug=False prevents Flask reloader process (keeps single process)
    # Use restart-app.sh for code reloads instead of auto-reload
    app.run(host='0.0.0.0', port=5006, debug=False)
