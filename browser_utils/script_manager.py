# --- browser_utils/script_manager.py ---
# Tampermonkey Script Management Module - Dynamic mounting and injection functionality

import os
import json
import logging
from typing import Dict, List, Optional, Any
from playwright.async_api import Page as AsyncPage

logger = logging.getLogger("AIStudioProxyServer")

class ScriptManager:
    """Tampermonkey Script Manager - Responsible for dynamic loading and script injection"""
    
    def __init__(self, script_dir: str = "browser_utils"):
        self.script_dir = script_dir
        self.loaded_scripts: Dict[str, str] = {}
        self.model_configs: Dict[str, List[Dict[str, Any]]] = {}
        
    def load_script(self, script_name: str) -> Optional[str]:
        """Load specified JavaScript script file"""
        script_path = os.path.join(self.script_dir, script_name)
        
        if not os.path.exists(script_path):
            logger.error(f"Script file does not exist: {script_path}")
            return None
            
        try:
            with open(script_path, 'r', encoding='utf-8') as f:
                script_content = f.read()
                self.loaded_scripts[script_name] = script_content
                logger.info(f"Successfully loaded script: {script_name}")
                return script_content
        except Exception as e:
            logger.error(f"Failed to load script {script_name}: {e}")
            return None
    
    def load_model_config(self, config_path: str) -> Optional[List[Dict[str, Any]]]:
        """Load model configuration file"""
        if not os.path.exists(config_path):
            logger.warning(f"Model config file does not exist: {config_path}")
            return None
            
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
                models = config_data.get('models', [])
                self.model_configs[config_path] = models
                logger.info(f"Successfully loaded model config: {len(models)} models")
                return models
        except Exception as e:
            logger.error(f"Failed to load model config {config_path}: {e}")
            return None
    
    def generate_dynamic_script(self, base_script: str, models: List[Dict[str, Any]],
                              script_version: str = "dynamic") -> str:
        """Generate dynamic script content based on model configuration"""
        try:
            # Build JavaScript code for model list
            models_js = "const MODELS_TO_INJECT = [\n"
            for model in models:
                name = model.get('name', '')
                display_name = model.get('displayName', model.get('display_name', ''))
                description = model.get('description', f'Model injected by script {script_version}')
                
                # If displayName does not contain version info, add it
                if f"(Script {script_version})" not in display_name:
                    display_name = f"{display_name} (Script {script_version})"
                
                models_js += f"""       {{
          name: '{name}',
          displayName: `{display_name}`,
          description: `{description}`
       }},\n"""
            
            models_js += "    ];"
            
            # Replace model definition part in the script
            # Find start and end markers for model definition
            start_marker = "const MODELS_TO_INJECT = ["
            end_marker = "];"
            
            start_idx = base_script.find(start_marker)
            if start_idx == -1:
                logger.error("Model definition start marker not found")
                return base_script
                
            # Find corresponding end marker
            bracket_count = 0
            end_idx = start_idx + len(start_marker)
            found_end = False
            
            for i in range(end_idx, len(base_script)):
                if base_script[i] == '[':
                    bracket_count += 1
                elif base_script[i] == ']':
                    if bracket_count == 0:
                        end_idx = i + 1
                        found_end = True
                        break
                    bracket_count -= 1
            
            if not found_end:
                logger.error("Model definition end marker not found")
                return base_script
            
            # Replace model definition part
            new_script = (base_script[:start_idx] +
                         models_js +
                         base_script[end_idx:])
            
            # Update version number
            new_script = new_script.replace(
                f'const SCRIPT_VERSION = "v1.6";',
                f'const SCRIPT_VERSION = "{script_version}";'
            )
            
            logger.info(f"Successfully generated dynamic script, containing {len(models)} models")
            return new_script
            
        except Exception as e:
            logger.error(f"Failed to generate dynamic script: {e}")
            return base_script
    
    async def inject_script_to_page(self, page: AsyncPage, script_content: str,
                                  script_name: str = "injected_script") -> bool:
        """Inject script into the page"""
        try:
            # Remove UserScript headers since we are injecting directly, not via Tampermonkey
            cleaned_script = self._clean_userscript_headers(script_content)
            
            # Inject script
            await page.add_init_script(cleaned_script)
            logger.info(f"Successfully injected script to page: {script_name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to inject script to page {script_name}: {e}")
            return False
    
    def _clean_userscript_headers(self, script_content: str) -> str:
        """Clean UserScript headers"""
        lines = script_content.split('\n')
        cleaned_lines = []
        in_userscript_block = False
        
        for line in lines:
            if line.strip().startswith('// ==UserScript=='):
                in_userscript_block = True
                continue
            elif line.strip().startswith('// ==/UserScript=='):
                in_userscript_block = False
                continue
            elif in_userscript_block:
                continue
            else:
                cleaned_lines.append(line)
        
        return '\n'.join(cleaned_lines)
    
    async def setup_model_injection(self, page: AsyncPage,
                                  script_name: str = "more_modles.js") -> bool:
        """Setup model injection - Inject Tampermonkey script directly"""

        # Check if script file exists
        script_path = os.path.join(self.script_dir, script_name)
        if not os.path.exists(script_path):
            # Script file does not exist, silently skip injection
            return False

        logger.info("Starting model injection setup...")

        # Load Tampermonkey script
        script_content = self.load_script(script_name)
        if not script_content:
            return False

        # Inject original script directly (without modification)
        return await self.inject_script_to_page(page, script_content, script_name)


# 全局脚本管理器实例
script_manager = ScriptManager()
