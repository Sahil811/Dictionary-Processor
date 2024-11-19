import json
import os
import concurrent.futures
import time
import random
from functools import partial
from googletrans import Translator
from tenacity import retry, stop_after_attempt, wait_exponential

class DictionaryProcessor:
    def __init__(self, input_file, output_folder):
        # Ensure output folder exists
        os.makedirs(output_folder, exist_ok=True)
        
        self.input_file = input_file
        self.output_folder = output_folder
        self.output_file = os.path.join(output_folder, 'japanese_dictionary_hindi.json')
        
        # Translation setup with retry mechanism
        self.translator = Translator()
        
        # Translation cache to avoid repeated translations
        self.translation_cache = self._load_translation_cache()
        
        # Load existing data or initialize
        self.processed_data = self._load_existing_data()
    
    def _load_translation_cache(self):
        """Load existing translation cache"""
        cache_file = os.path.join(self.output_folder, '.translation_cache.json')
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            return {}
    
    def _save_translation_cache(self):
        """Save translation cache"""
        cache_file = os.path.join(self.output_folder, '.translation_cache.json')
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(self.translation_cache, f, ensure_ascii=False, indent=2)
    
    def _load_existing_data(self):
        # Load existing processed data
        try:
            with open(self.output_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            return []
    
    def _save_progress(self, entry):
        # Append new entry and save to file
        self.processed_data.append(entry)
        with open(self.output_file, 'w', encoding='utf-8') as f:
            json.dump(self.processed_data, f, ensure_ascii=False, indent=2)
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    def _translate_meaning(self, meaning):
        try:
            # Check translation cache first
            if meaning in self.translation_cache:
                return self.translation_cache[meaning]
            
            # Translate with googletrans
            translation = self.translator.translate(meaning, src='en', dest='hi')
            translated_text = translation.text
            
            # Cache the translation
            self.translation_cache[meaning] = translated_text
            self._save_translation_cache()
            
            # Add random delay to prevent rate limiting
            time.sleep(random.uniform(0.5, 1.5))
            
            return translated_text
        except Exception as e:
            print(f"Translation error for '{meaning}': {e}")
            return meaning
    
    def _process_single_entry(self, entry):
        # Extract kanji and kana
        kanji_texts = [k['text'] for k in entry['kanji']]
        kana_texts = [k['text'] for k in entry['kana']]
        
        # Extract English meanings
        english_meanings = [gloss['text'] for sense in entry['sense'] for gloss in sense['gloss'] if gloss['lang'] == 'eng']
        
        # Translate meanings to Hindi
        hindi_meanings = []
        for meaning in english_meanings:
            # Translate and add non-empty translations
            hindi_translation = self._translate_meaning(meaning)
            if hindi_translation and hindi_translation.strip():
                hindi_meanings.append(hindi_translation)
        
        # Create output entry
        output_entry = {
            'kanji': kanji_texts,
            'kana': kana_texts,
            'meaning': hindi_meanings
        }
        
        return output_entry
    
    def process_dictionary(self, max_workers=4):
        # Read the input JSON file
        with open(self.input_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Filter out already processed entries
        entries_to_process = data['words'][len(self.processed_data):]
        
        # Use concurrent processing
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Process entries in parallel
            for processed_entry in executor.map(self._process_single_entry, entries_to_process):
                # Save each processed entry immediately
                self._save_progress(processed_entry)
                print(f"Processed entry: {processed_entry['kanji']}")
        
        print("Processing complete!")
        return self.output_file

# Example usage
def main():
    input_file = './jmdict-eng.json\jmdict-eng-3.3.1.json'
    output_folder = 'output'
    
    processor = DictionaryProcessor(input_file, output_folder)
    processor.process_dictionary()

if __name__ == '__main__':
    main()