import json
import os
from googletrans import Translator
from tenacity import retry, stop_after_attempt, wait_exponential
import time
from pathlib import Path
import hashlib

class RealTimeJsonTranslator:
    def __init__(self, input_dir, output_dir):
        self.input_directory = input_dir
        self.output_directory = output_dir
        self.translator = Translator()
        self.ensure_output_directory()
        self.translation_cache = self.load_translation_cache()
        
    def ensure_output_directory(self):
        """Create output directory and cache file if they don't exist"""
        if not os.path.exists(self.output_directory):
            os.makedirs(self.output_directory)
            
    def get_cache_file_path(self):
        """Get the path for the translation cache file"""
        return os.path.join(self.output_directory, '.translation_cache.json')
            
    def load_translation_cache(self):
        """Load existing translations from cache file"""
        cache_file = self.get_cache_file_path()
        if os.path.exists(cache_file):
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return {}
        return {}
    
    def save_translation_cache(self):
        """Save translations to cache file"""
        cache_file = self.get_cache_file_path()
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(self.translation_cache, f, ensure_ascii=False, indent=2)
            
    def get_content_hash(self, content):
        """Generate a hash for content to check if it's been translated"""
        if isinstance(content, str):
            return hashlib.md5(content.encode()).hexdigest()
        return None
            
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    def translate_text(self, text):
        """Translate text from English to Hindi with retry logic"""
        try:
            if not isinstance(text, str) or not text.strip():
                return text
                
            # Check if we already have this translation
            content_hash = self.get_content_hash(text)
            if content_hash in self.translation_cache:
                return self.translation_cache[content_hash]
                
            # Only translate if it's English text (basic check)
            if text.isascii():
                result = self.translator.translate(text, src='en', dest='hi')
                translated_text = result.text
                
                # Cache the translation
                self.translation_cache[content_hash] = translated_text
                self.save_translation_cache()
                
                print(f"Translated: {text} -> {translated_text}")
                return translated_text
            return text
            
        except Exception as e:
            print(f"Translation error: {e}")
            raise
    
    def update_json_file(self, input_file, current_data):
        """Update the JSON file with current translations"""
        output_file = os.path.join(self.output_directory, os.path.basename(input_file))
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(current_data, f, ensure_ascii=False, indent=2)
            
    def translate_content_list(self, content_list, input_file, data, entry_index):
        """Translate content items in a list and update file in real-time"""
        if isinstance(content_list, list):
            modified = False
            for i, item in enumerate(content_list):
                if isinstance(item, dict) and 'content' in item:
                    if isinstance(item['content'], str):
                        original_content = item['content']
                        item['content'] = self.translate_text(original_content)
                        if original_content != item['content']:
                            modified = True
                    elif isinstance(item['content'], list):
                        if self.translate_content_list(item['content'], input_file, data, entry_index):
                            modified = True
                            
            if modified:
                self.update_json_file(input_file, data)
            return modified
        return False
        
    def process_file(self, input_file):
        """Process a single JSON file with real-time updates"""
        try:
            with open(input_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            # Create output file if it doesn't exist
            output_file = os.path.join(self.output_directory, os.path.basename(input_file))
            if not os.path.exists(output_file):
                with open(output_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                    
            # Process each entry in the JSON array
            for entry_index, entry in enumerate(data):
                if len(entry) >= 6 and isinstance(entry[5], list):
                    for item in entry[5]:
                        if 'type' in item and item['type'] == 'structured-content':
                            if isinstance(item.get('content'), list):
                                for content_item in item['content']:
                                    self.translate_content_list(
                                        [content_item], 
                                        input_file,
                                        data,
                                        entry_index
                                    )
                                    
                            # Update file after processing each structured content
                            self.update_json_file(input_file, data)
                            
            print(f"Completed processing: {input_file}")
            
        except Exception as e:
            print(f"Error processing {input_file}: {e}")
            
    def process_directory(self):
        """Process all JSON files in the input directory"""
        for filename in os.listdir(self.input_directory):
            if filename.startswith('term_bank_') and filename.endswith('.json'):
                input_file = os.path.join(self.input_directory, filename)
                print(f"Processing {filename}...")
                self.process_file(input_file)
                # Add a small delay to avoid hitting API limits
                time.sleep(1)

def main():
    input_directory = 'jitendex-yomitan'
    output_directory = 'jitendex-yomitan_hindi'
    
    translator = RealTimeJsonTranslator(input_directory, output_directory)
    translator.process_directory()

if __name__ == "__main__":
    main()