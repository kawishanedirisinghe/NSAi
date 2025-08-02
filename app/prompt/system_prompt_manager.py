import os
import json
import requests
import yaml
import toml
from typing import Dict, List, Optional, Any
from pathlib import Path
import logging
from datetime import datetime
import hashlib
import re

logger = logging.getLogger(__name__)

class SystemPromptManager:
    def __init__(self, cache_dir: str = "prompt_cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
        self.prompts: Dict[str, Dict] = {}
        self.categories: Dict[str, List[str]] = {}
        self.metadata_file = self.cache_dir / "metadata.json"
        self.load_metadata()
        
        # GitHub repository configuration
        self.github_repo = "x1xhlol/system-prompts-and-models-of-ai-tools"
        self.github_api_base = "https://api.github.com/repos"
        self.github_raw_base = "https://raw.githubusercontent.com"
        
    def load_metadata(self):
        """Load metadata from cache"""
        if self.metadata_file.exists():
            try:
                with open(self.metadata_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.prompts = data.get('prompts', {})
                    self.categories = data.get('categories', {})
                    logger.info(f"Loaded {len(self.prompts)} prompts from cache")
            except Exception as e:
                logger.error(f"Error loading metadata: {e}")
    
    def save_metadata(self):
        """Save metadata to cache"""
        try:
            data = {
                'prompts': self.prompts,
                'categories': self.categories,
                'last_updated': datetime.now().isoformat()
            }
            with open(self.metadata_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Error saving metadata: {e}")
    
    def fetch_github_content(self, path: str = "") -> Optional[Dict]:
        """Fetch content from GitHub repository"""
        try:
            url = f"{self.github_api_base}/{self.github_repo}/contents/{path}"
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error fetching GitHub content: {e}")
            return None
    
    def download_file(self, url: str, local_path: Path) -> bool:
        """Download file from URL"""
        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            
            local_path.parent.mkdir(parents=True, exist_ok=True)
            with open(local_path, 'w', encoding='utf-8') as f:
                f.write(response.text)
            return True
        except Exception as e:
            logger.error(f"Error downloading file {url}: {e}")
            return False
    
    def parse_prompt_file(self, file_path: Path) -> Optional[Dict]:
        """Parse prompt file and extract metadata"""
        try:
            content = file_path.read_text(encoding='utf-8')
            file_ext = file_path.suffix.lower()
            
            if file_ext == '.json':
                data = json.loads(content)
                return self.extract_prompt_metadata(data, file_path.name)
            elif file_ext == '.yaml' or file_ext == '.yml':
                data = yaml.safe_load(content)
                return self.extract_prompt_metadata(data, file_path.name)
            elif file_ext == '.toml':
                data = toml.loads(content)
                return self.extract_prompt_metadata(data, file_path.name)
            elif file_ext == '.md':
                return self.parse_markdown_prompt(content, file_path.name)
            elif file_ext == '.txt':
                return self.parse_text_prompt(content, file_path.name)
            else:
                return self.parse_generic_prompt(content, file_path.name)
                
        except Exception as e:
            logger.error(f"Error parsing file {file_path}: {e}")
            return None
    
    def extract_prompt_metadata(self, data: Dict, filename: str) -> Dict:
        """Extract metadata from structured prompt files"""
        prompt_id = data.get('id', filename.replace('.', '_'))
        
        return {
            'id': prompt_id,
            'name': data.get('name', filename),
            'description': data.get('description', ''),
            'content': data.get('content', data.get('prompt', '')),
            'category': data.get('category', 'general'),
            'tags': data.get('tags', []),
            'version': data.get('version', '1.0'),
            'author': data.get('author', ''),
            'created': data.get('created', ''),
            'updated': data.get('updated', ''),
            'filename': filename,
            'type': 'structured'
        }
    
    def parse_markdown_prompt(self, content: str, filename: str) -> Dict:
        """Parse markdown prompt files"""
        lines = content.split('\n')
        metadata = {}
        prompt_content = []
        in_content = False
        
        for line in lines:
            if line.startswith('---'):
                in_content = not in_content
                continue
            
            if not in_content and line.startswith('#'):
                # Extract title
                if not metadata.get('name'):
                    metadata['name'] = line.lstrip('#').strip()
            elif not in_content and ':' in line:
                # Extract metadata
                key, value = line.split(':', 1)
                metadata[key.strip().lower()] = value.strip()
            elif in_content:
                prompt_content.append(line)
        
        prompt_id = metadata.get('id', filename.replace('.md', '').replace('.', '_'))
        
        return {
            'id': prompt_id,
            'name': metadata.get('name', filename),
            'description': metadata.get('description', ''),
            'content': '\n'.join(prompt_content).strip(),
            'category': metadata.get('category', 'general'),
            'tags': metadata.get('tags', '').split(',') if metadata.get('tags') else [],
            'version': metadata.get('version', '1.0'),
            'author': metadata.get('author', ''),
            'created': metadata.get('created', ''),
            'updated': metadata.get('updated', ''),
            'filename': filename,
            'type': 'markdown'
        }
    
    def parse_text_prompt(self, content: str, filename: str) -> Dict:
        """Parse plain text prompt files"""
        lines = content.split('\n')
        name = filename.replace('.txt', '').replace('_', ' ').title()
        
        # Try to extract first line as title
        if lines and lines[0].strip():
            name = lines[0].strip()
            content = '\n'.join(lines[1:]).strip()
        
        prompt_id = filename.replace('.txt', '').replace('.', '_')
        
        return {
            'id': prompt_id,
            'name': name,
            'description': f'Text prompt from {filename}',
            'content': content,
            'category': 'general',
            'tags': [],
            'version': '1.0',
            'author': '',
            'created': '',
            'updated': '',
            'filename': filename,
            'type': 'text'
        }
    
    def parse_generic_prompt(self, content: str, filename: str) -> Dict:
        """Parse generic prompt files"""
        prompt_id = filename.replace('.', '_')
        name = filename.replace('_', ' ').title()
        
        return {
            'id': prompt_id,
            'name': name,
            'description': f'Prompt from {filename}',
            'content': content.strip(),
            'category': 'general',
            'tags': [],
            'version': '1.0',
            'author': '',
            'created': '',
            'updated': '',
            'filename': filename,
            'type': 'generic'
        }
    
    def sync_from_github(self, force: bool = False) -> bool:
        """Sync prompts from GitHub repository"""
        try:
            logger.info("Starting GitHub sync...")
            
            # Get repository contents
            contents = self.fetch_github_content()
            if not contents:
                return False
            
            # Process each item
            for item in contents:
                if item['type'] == 'file':
                    self.process_github_file(item)
                elif item['type'] == 'dir':
                    self.process_github_directory(item['path'])
            
            # Save metadata
            self.save_metadata()
            logger.info(f"GitHub sync completed. Total prompts: {len(self.prompts)}")
            return True
            
        except Exception as e:
            logger.error(f"Error syncing from GitHub: {e}")
            return False
    
    def process_github_file(self, file_info: Dict):
        """Process a single file from GitHub"""
        try:
            filename = file_info['name']
            download_url = file_info['download_url']
            file_path = self.cache_dir / filename
            
            # Check if file needs updating
            if file_path.exists() and not self.should_update_file(file_info):
                return
            
            # Download file
            if self.download_file(download_url, file_path):
                # Parse prompt
                prompt_data = self.parse_prompt_file(file_path)
                if prompt_data:
                    self.prompts[prompt_data['id']] = prompt_data
                    self.add_to_category(prompt_data['category'], prompt_data['id'])
                    logger.info(f"Processed prompt: {prompt_data['name']}")
                    
        except Exception as e:
            logger.error(f"Error processing GitHub file {file_info.get('name', 'unknown')}: {e}")
    
    def process_github_directory(self, dir_path: str):
        """Process a directory from GitHub"""
        try:
            contents = self.fetch_github_content(dir_path)
            if not contents:
                return
            
            for item in contents:
                if item['type'] == 'file':
                    self.process_github_file(item)
                elif item['type'] == 'dir':
                    self.process_github_directory(item['path'])
                    
        except Exception as e:
            logger.error(f"Error processing GitHub directory {dir_path}: {e}")
    
    def should_update_file(self, file_info: Dict) -> bool:
        """Check if file should be updated based on modification time"""
        # This is a simplified check - in a real implementation you might want to
        # compare hashes or use GitHub's API to check modification times
        return True
    
    def add_to_category(self, category: str, prompt_id: str):
        """Add prompt to category"""
        if category not in self.categories:
            self.categories[category] = []
        if prompt_id not in self.categories[category]:
            self.categories[category].append(prompt_id)
    
    def get_prompt(self, prompt_id: str) -> Optional[Dict]:
        """Get a specific prompt by ID"""
        return self.prompts.get(prompt_id)
    
    def get_prompts_by_category(self, category: str) -> List[Dict]:
        """Get all prompts in a category"""
        prompt_ids = self.categories.get(category, [])
        return [self.prompts.get(pid) for pid in prompt_ids if self.prompts.get(pid)]
    
    def search_prompts(self, query: str) -> List[Dict]:
        """Search prompts by query"""
        results = []
        query_lower = query.lower()
        
        for prompt in self.prompts.values():
            if (query_lower in prompt['name'].lower() or
                query_lower in prompt['description'].lower() or
                query_lower in prompt['content'].lower() or
                any(query_lower in tag.lower() for tag in prompt.get('tags', []))):
                results.append(prompt)
        
        return results
    
    def get_categories(self) -> List[str]:
        """Get all available categories"""
        return list(self.categories.keys())
    
    def create_custom_prompt(self, name: str, content: str, category: str = "custom", 
                           description: str = "", tags: List[str] = None) -> str:
        """Create a custom prompt"""
        prompt_id = f"custom_{hashlib.md5(name.encode()).hexdigest()[:8]}"
        
        prompt_data = {
            'id': prompt_id,
            'name': name,
            'description': description,
            'content': content,
            'category': category,
            'tags': tags or [],
            'version': '1.0',
            'author': 'user',
            'created': datetime.now().isoformat(),
            'updated': datetime.now().isoformat(),
            'filename': f"{prompt_id}.json",
            'type': 'custom'
        }
        
        self.prompts[prompt_id] = prompt_data
        self.add_to_category(category, prompt_id)
        self.save_metadata()
        
        return prompt_id
    
    def update_prompt(self, prompt_id: str, updates: Dict) -> bool:
        """Update an existing prompt"""
        if prompt_id not in self.prompts:
            return False
        
        prompt = self.prompts[prompt_id]
        prompt.update(updates)
        prompt['updated'] = datetime.now().isoformat()
        
        self.save_metadata()
        return True
    
    def delete_prompt(self, prompt_id: str) -> bool:
        """Delete a prompt"""
        if prompt_id not in self.prompts:
            return False
        
        prompt = self.prompts[prompt_id]
        category = prompt.get('category', 'general')
        
        # Remove from category
        if category in self.categories and prompt_id in self.categories[category]:
            self.categories[category].remove(prompt_id)
        
        # Remove prompt
        del self.prompts[prompt_id]
        self.save_metadata()
        
        return True
    
    def export_prompt(self, prompt_id: str, format: str = "json") -> Optional[str]:
        """Export a prompt in specified format"""
        prompt = self.get_prompt(prompt_id)
        if not prompt:
            return None
        
        if format == "json":
            return json.dumps(prompt, indent=2, ensure_ascii=False)
        elif format == "yaml":
            return yaml.dump(prompt, default_flow_style=False, allow_unicode=True)
        elif format == "text":
            return prompt['content']
        else:
            return None
    
    def get_prompt_statistics(self) -> Dict:
        """Get statistics about prompts"""
        total_prompts = len(self.prompts)
        categories = len(self.categories)
        custom_prompts = len([p for p in self.prompts.values() if p.get('type') == 'custom'])
        
        # Count by type
        type_counts = {}
        for prompt in self.prompts.values():
            prompt_type = prompt.get('type', 'unknown')
            type_counts[prompt_type] = type_counts.get(prompt_type, 0) + 1
        
        return {
            'total_prompts': total_prompts,
            'categories': categories,
            'custom_prompts': custom_prompts,
            'type_counts': type_counts,
            'last_updated': datetime.now().isoformat()
        }
    
    def validate_prompt(self, prompt_id: str) -> Dict:
        """Validate a prompt and return issues"""
        prompt = self.get_prompt(prompt_id)
        if not prompt:
            return {'valid': False, 'issues': ['Prompt not found']}
        
        issues = []
        
        # Check required fields
        required_fields = ['name', 'content']
        for field in required_fields:
            if not prompt.get(field):
                issues.append(f"Missing required field: {field}")
        
        # Check content length
        content = prompt.get('content', '')
        if len(content) < 10:
            issues.append("Content too short (minimum 10 characters)")
        elif len(content) > 10000:
            issues.append("Content too long (maximum 10,000 characters)")
        
        # Check for common issues
        if content and not content.strip():
            issues.append("Content is empty or only whitespace")
        
        return {
            'valid': len(issues) == 0,
            'issues': issues,
            'prompt_id': prompt_id
        }

# Advanced prompt templates
class AdvancedPromptTemplates:
    @staticmethod
    def create_coding_assistant_prompt() -> str:
        return """You are an expert software developer and coding assistant. Your role is to help users write, debug, and optimize code across multiple programming languages and frameworks.

**Core Capabilities:**
- Write clean, efficient, and well-documented code
- Debug and fix issues in existing code
- Optimize performance and improve code quality
- Explain complex programming concepts
- Provide best practices and design patterns
- Review code and suggest improvements

**Response Format:**
1. **Analysis**: Understand the problem and requirements
2. **Solution**: Provide clear, working code with explanations
3. **Explanation**: Break down the solution and explain key concepts
4. **Best Practices**: Suggest improvements and alternatives
5. **Testing**: Provide test cases or validation steps

**Code Standards:**
- Follow language-specific conventions and style guides
- Include proper error handling and edge cases
- Write self-documenting code with clear variable names
- Add comments for complex logic
- Consider security implications
- Optimize for readability and maintainability

Always ask clarifying questions when requirements are unclear, and provide multiple approaches when appropriate."""

    @staticmethod
    def create_ai_tool_expert_prompt() -> str:
        return """You are an expert in AI tools, models, and systems. You have deep knowledge of various AI frameworks, APIs, and tools including but not limited to:

**AI Models & APIs:**
- OpenAI GPT models (GPT-3.5, GPT-4, GPT-4 Turbo)
- Anthropic Claude models
- Google Gemini models
- Meta LLaMA models
- Local models (Ollama, LM Studio, etc.)

**AI Tools & Frameworks:**
- LangChain, LlamaIndex, AutoGen
- Cursor, Manus, Same
- MCP (Model Context Protocol)
- Various AI agent frameworks
- Prompt engineering tools

**System Prompts & Optimization:**
- Advanced prompt engineering techniques
- System prompt design and optimization
- Context management and token optimization
- Multi-agent system design
- Tool integration and automation

**Your Expertise:**
- Help users optimize their AI workflows
- Design effective system prompts
- Integrate multiple AI tools and APIs
- Troubleshoot AI tool issues
- Provide best practices for AI development
- Explain complex AI concepts and architectures

**Response Approach:**
1. **Assessment**: Understand the user's AI setup and goals
2. **Recommendation**: Suggest optimal tools and configurations
3. **Implementation**: Provide specific code and configuration examples
4. **Optimization**: Help improve performance and efficiency
5. **Best Practices**: Share industry standards and tips

Always consider the user's specific use case, technical constraints, and desired outcomes when providing recommendations."""

    @staticmethod
    def create_web_development_prompt() -> str:
        return """You are a full-stack web development expert specializing in modern web technologies and best practices.

**Frontend Technologies:**
- React, Vue, Angular, Svelte
- TypeScript, JavaScript (ES6+)
- CSS3, SCSS, Tailwind CSS
- Web Components, Progressive Web Apps
- Modern build tools (Vite, Webpack, etc.)

**Backend Technologies:**
- Node.js, Python (Django, Flask, FastAPI)
- PHP, Ruby on Rails, Java Spring
- Databases: PostgreSQL, MySQL, MongoDB, Redis
- APIs: REST, GraphQL, WebSockets
- Cloud platforms: AWS, Azure, Google Cloud

**DevOps & Tools:**
- Docker, Kubernetes, CI/CD
- Git, GitHub, GitLab
- Testing frameworks and tools
- Performance optimization
- Security best practices

**Your Approach:**
1. **Requirements Analysis**: Understand project goals and constraints
2. **Architecture Design**: Suggest optimal technology stack
3. **Implementation**: Provide clean, production-ready code
4. **Testing**: Include unit and integration tests
5. **Deployment**: Guide through deployment process
6. **Maintenance**: Suggest monitoring and maintenance strategies

Always consider scalability, security, performance, and user experience in your recommendations."""

# Initialize the prompt manager
prompt_manager = SystemPromptManager()

# Pre-load some advanced templates
def initialize_advanced_templates():
    """Initialize advanced prompt templates"""
    templates = {
        'coding_assistant': AdvancedPromptTemplates.create_coding_assistant_prompt(),
        'ai_tool_expert': AdvancedPromptTemplates.create_ai_tool_expert_prompt(),
        'web_development': AdvancedPromptTemplates.create_web_development_prompt(),
    }
    
    for name, content in templates.items():
        prompt_manager.create_custom_prompt(
            name=f"Advanced {name.replace('_', ' ').title()}",
            content=content,
            category="advanced_templates",
            description=f"Advanced system prompt for {name.replace('_', ' ')}",
            tags=["advanced", "template", name]
        )

# Initialize templates on module load
initialize_advanced_templates()