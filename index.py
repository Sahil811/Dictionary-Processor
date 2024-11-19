import json
import os
import argostranslate.package
import argostranslate.translate
from tenacity import retry, stop_after_attempt, wait_exponential
import time
from pathlib import Path
import hashlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any
import queue
from threading import Lock

class RealTimeJsonTranslator:
    def __init__(self, input_dir, output_dir, from_code='en', to_code='hi', 
                 batch_size=50, num_workers=4):
        self.input_directory = input_dir
        self.output_directory = output_dir
        self.from_code = from_code
        self.to_code = to_code
        self.batch_size = batch_size
        self.num_workers = num_workers
        self.ensure_output_directory()
        self.translation_cache = self.load_translation_cache()
        self.cache_lock = Lock()
        self.translation_queue = queue.Queue()
        self.setup_translator()
        
    def setup_translator(self):
        """Initialize Argos Translate with required language packages"""
        argostranslate.package.update_package_index()
        available_packages = argostranslate.package.get_available_packages()
        package_to_install = next(
            filter(
                lambda x: x.from_code == self.from_code and x.to_code == self.to_code,
                available_packages
            ),
            None
        )
        
        if package_to_install is None:
            raise ValueError(f"Translation package not found for {self.from_code} to {self.to_code}")
            
        argostranslate.package.install_from_path(package_to_install.download())
        
    def ensure_output_directory(self):
        if not os.path.exists(self.output_directory):
            os.makedirs(self.output_directory)
            
    def get_cache_file_path(self):
        return os.path.join(self.output_directory, '.translation_cache.json')
            
    def load_translation_cache(self):
        cache_file = self.get_cache_file_path()
        if os.path.exists(cache_file):
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return {}
        return {}
    
    def save_translation_cache(self):
        cache_file = self.get_cache_file_path()
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(self.translation_cache, f, ensure_ascii=False, indent=2)
            
    def get_content_hash(self, content):
        if isinstance(content, str):
            return hashlib.md5(content.encode()).hexdigest()
        return None

    def batch_translate(self, texts: List[str]) -> List[str]:
        """Translate a batch of texts"""
        try:
            translations = []
            for text in texts:
                translated = argostranslate.translate.translate(
                    text,
                    self.from_code,
                    self.to_code
                )
                translations.append(translated)
            return translations
        except Exception as e:
            print(f"Batch translation error: {e}")
            raise

    def translation_worker(self):
        """Worker function for parallel translation processing"""
        batch = []
        while True:
            try:
                item = self.translation_queue.get(timeout=1)
                if item is None:  # Poison pill
                    break
                
                text, content_hash = item
                batch.append((text, content_hash))
                
                # Process batch when it reaches batch_size
                if len(batch) >= self.batch_size:
                    self._process_batch(batch)
                    batch = []
                    
            except queue.Empty:
                if batch:  # Process remaining items
                    self._process_batch(batch)
                break
                
    def _process_batch(self, batch):
        """Process a batch of translations"""
        texts = [item[0] for item in batch]
        content_hashes = [item[1] for item in batch]
        
        translations = self.batch_translate(texts)
        
        with self.cache_lock:
            for text, translation, content_hash in zip(texts, translations, content_hashes):
                self.translation_cache[content_hash] = translation
                print(f"Translated: {text} -> {translation}")
            self.save_translation_cache()

    def translate_text(self, text):
        """Queue text for translation if not in cache"""
        try:
            if not isinstance(text, str) or not text.strip():
                return text
                
            content_hash = self.get_content_hash(text)
            
            with self.cache_lock:
                if content_hash in self.translation_cache:
                    return self.translation_cache[content_hash]
                
            if any(ord(char) < 128 for char in text):
                self.translation_queue.put((text, content_hash))
                return text  # Return original text, will be updated in next pass
            return text
            
        except Exception as e:
            print(f"Translation error: {e}")
            raise
    
    def process_file(self, input_file):
        """Process a single JSON file with parallel translation"""
        try:
            with open(input_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            output_file = os.path.join(self.output_directory, os.path.basename(input_file))
            if not os.path.exists(output_file):
                with open(output_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
            
            # First pass: Queue all translations
            self._process_content(data)
            
            # Start translation workers
            with ThreadPoolExecutor(max_workers=self.num_workers) as executor:
                workers = [executor.submit(self.translation_worker) 
                          for _ in range(self.num_workers)]
                
                # Wait for all translations to complete
                for worker in as_completed(workers):
                    worker.result()
            
            # Second pass: Update with translations
            self._process_content(data)
            self.update_json_file(input_file, data)
            
            print(f"Completed processing: {input_file}")
            
        except Exception as e:
            print(f"Error processing {input_file}: {e}")
            
    def _process_content(self, data):
        """Process all content in the data structure"""
        for entry_index, entry in enumerate(data):
            if len(entry) >= 6 and isinstance(entry[5], list):
                for item in entry[5]:
                    if 'type' in item and item['type'] == 'structured-content':
                        if isinstance(item.get('content'), list):
                            for content_item in item['content']:
                                self._process_content_item(content_item)
                                
    def _process_content_item(self, item):
        """Process a single content item"""
        if isinstance(item, dict) and 'content' in item:
            if isinstance(item['content'], str):
                item['content'] = self.translate_text(item['content'])
            elif isinstance(item['content'], list):
                for sub_item in item['content']:
                    self._process_content_item(sub_item)
    
    def update_json_file(self, input_file, current_data):
        output_file = os.path.join(self.output_directory, os.path.basename(input_file))
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(current_data, f, ensure_ascii=False, indent=2)
            
    def process_directory(self):
        for filename in os.listdir(self.input_directory):
            if filename.startswith('term_bank_') and filename.endswith('.json'):
                input_file = os.path.join(self.input_directory, filename)
                print(f"Processing {filename}...")
                self.process_file(input_file)

def main():
    input_directory = 'jitendex-yomitan'
    output_directory = 'jitendex-yomitan_hindi'
    
    translator = RealTimeJsonTranslator(
        input_directory,
        output_directory,
        from_code='en',
        to_code='hi',
        batch_size=500,  # Adjust based on your needs
        num_workers=12   # Adjust based on your CPU cores
    )
    translator.process_directory()

if __name__ == "__main__":
    main()