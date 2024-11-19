import json
import os
import concurrent.futures
import argostranslate.package
import argostranslate.translate
import traceback
import sys

class DictionaryProcessor:
    def __init__(self, input_file, output_folder, batch_size=500):
        # Ensure output folder exists
        os.makedirs(output_folder, exist_ok=True)
        
        self.input_file = os.path.normpath(input_file)
        self.output_folder = output_folder
        self.output_file = os.path.join(output_folder, 'japanese_dictionary_hindi.json')
        self.cache_file = os.path.join(output_folder, '.translation_cache.json')
        self.progress_file = os.path.join(output_folder, '.processing_progress.json')
        
        # Batch processing configuration
        self.batch_size = batch_size
        
        # Setup translation and load cache
        self._setup_translation()
        self.translation_cache = self._load_translation_cache()
        
        # Load existing data and progress
        self.processed_data = self._load_existing_data()
        self.processing_progress = self._load_processing_progress()
    
    def _setup_translation(self):
        """Set up translation from English to Hindi"""
        try:
            argostranslate.package.update_package_index()
            available_packages = argostranslate.package.get_available_packages()
            
            translation_package = next(
                filter(
                    lambda x: x.from_code == 'en' and x.to_code == 'hi', 
                    available_packages
                ), 
                None
            )
            
            if translation_package:
                argostranslate.package.install_from_path(translation_package.download())
            else:
                raise ValueError("No English to Hindi translation package found")
        except Exception as e:
            print(f"Translation setup error: {e}")
            sys.exit(1)
    
    def _load_translation_cache(self):
        """Load existing translation cache"""
        try:
            with open(self.cache_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}
    
    def _save_translation_cache(self):
        """Save translation cache"""
        try:
            # Create a copy of the dictionary to avoid modification during iteration
            cache_copy = dict(self.translation_cache)
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(cache_copy, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Error saving translation cache: {e}")
    
    def _load_processing_progress(self):
        """Load processing progress"""
        try:
            with open(self.progress_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {'processed_batches': 0, 'total_batches': 0}
    
    def _save_processing_progress(self, processed_batches, total_batches):
        """Save processing progress"""
        try:
            with open(self.progress_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'processed_batches': processed_batches, 
                    'total_batches': total_batches
                }, f)
        except Exception as e:
            print(f"Error saving processing progress: {e}")
    
    def _load_existing_data(self):
        """Load existing processed data"""
        try:
            with open(self.output_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return []
    
    def _save_batch_progress(self, batch_entries, processed_batches, total_batches):
        """Save a batch of processed entries"""
        try:
            # Extend processed data
            self.processed_data.extend(batch_entries)
            
            # Write to output file
            with open(self.output_file, 'w', encoding='utf-8') as f:
                json.dump(self.processed_data, f, ensure_ascii=False, indent=2)
            
            # Update and save progress
            self._save_processing_progress(processed_batches, total_batches)
            
            print(f"Saved batch {processed_batches}/{total_batches} - {len(batch_entries)} entries")
        except Exception as e:
            print(f"Error saving batch progress: {e}")
            traceback.print_exc()
    
    def _translate_meaning(self, meaning):
        """Translate a single meaning"""
        try:
            # Check translation cache first
            if meaning in self.translation_cache:
                return self.translation_cache[meaning]
            
            # Translate using Argos Translate
            translated_text = argostranslate.translate.translate(meaning, 'en', 'hi')
            
            # Cache the translation
            self.translation_cache[meaning] = translated_text
            self._save_translation_cache()
            
            return translated_text
        except Exception as e:
            print(f"Translation error for '{meaning}': {e}")
            return meaning
    
    def _process_single_entry(self, entry):
        """Process a single dictionary entry"""
        # Extract kanji and kana
        kanji_texts = [k['text'] for k in entry['kanji']]
        kana_texts = [k['text'] for k in entry['kana']]
        
        # Extract English meanings
        english_meanings = [gloss['text'] for sense in entry['sense'] for gloss in sense['gloss'] if gloss['lang'] == 'eng']
        
        # Translate meanings to Hindi
        hindi_meanings = []
        for meaning in english_meanings:
            hindi_translation = self._translate_meaning(meaning)
            if hindi_translation and hindi_translation.strip():
                hindi_meanings.append(hindi_translation)
        
        # Create output entry
        return {
            'kanji': kanji_texts,
            'kana': kana_texts,
            'meaning': hindi_meanings
        }
    
    def process_dictionary(self, max_workers=4):
        """Process dictionary in batches"""
        try:
            # Read the input JSON file
            with open(self.input_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            words = data['words']
            total_batches = (len(words) + self.batch_size - 1) // self.batch_size
            start_batch = self.processing_progress.get('processed_batches', 0)
            
            # Update total_batches if needed
            if self.processing_progress.get('total_batches', 0) != total_batches:
                self._save_processing_progress(start_batch, total_batches)
            
            # Process in batches
            for batch_num in range(start_batch, total_batches):
                # Calculate batch range
                start_idx = batch_num * self.batch_size
                end_idx = min(start_idx + self.batch_size, len(words))
                batch_entries = words[start_idx:end_idx]
                
                # Process batch
                with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                    processed_batch = list(executor.map(self._process_single_entry, batch_entries))
                
                # Save batch progress
                self._save_batch_progress(processed_batch, batch_num + 1, total_batches)
                
                # Break if we've processed all entries
                if end_idx >= len(words):
                    break
        
        except Exception as e:
            print(f"Processing error: {e}")
            traceback.print_exc()
        
        print("Processing complete!")
        return self.output_file

# Example usage
def main():
    input_file = r'./jmdict-eng.json\jmdict-eng-3.3.1.json'
    output_folder = 'output'
    
    processor = DictionaryProcessor(input_file, output_folder, batch_size=500)
    processor.process_dictionary()

if __name__ == '__main__':
    main()
