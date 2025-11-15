import json
import google.generativeai as genai
import os
import re
from .weather_service import WeatherService

# Setup Gemini
API_KEY = "AIzaSyBilto_r5gM_gzk0pQAHHE8oz2ih8ZxMn4"
genai.configure(api_key=API_KEY)
model = genai.GenerativeModel("gemini-2.5-flash")

class CropChatBot:
    def __init__(self):
        # Load crop details
        current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        json_path = os.path.join(current_dir, 'crop_details_expanded_climate_fruits.json')
        with open(json_path, 'r', encoding='utf-8') as f:
            self.crop_data = json.load(f)
        
        # Initialize weather service
        self.weather_service = WeatherService()
            



    def extract_image_paths_from_response(self, response_text, user_query, chat_history=None):
        """Extract image paths based on Gemini's SHOW_IMAGES directive"""
        image_paths = []
        
        # Convert image paths to web-accessible URLs
        def convert_path_to_url(path):
            if path.startswith('./uploads/'):
                return '/media/' + path[10:]  # Remove './uploads/' and add '/media/'
            return path
        
        # Parse the SHOW_IMAGES directive from Gemini's response
        import re
        
        # Look for SHOW_IMAGES: item1, item2, item3 pattern (with or without brackets)
        show_images_pattern = r'SHOW_IMAGES\s*:\s*(?:\[(.*?)\]|([^"\n]+))'
        matches = re.search(show_images_pattern, response_text, re.IGNORECASE | re.DOTALL)
        
        if not matches:
            return image_paths
        
        # Extract the items from the match (either from brackets or direct format)
        items_string = matches.group(1) or matches.group(2) or ''
        items_string = items_string.strip()
        if not items_string:
            return image_paths
        
        # Split items and clean them
        requested_items = []
        for item in items_string.split(','):
            item = item.strip().strip('"\'')
            if item:
                requested_items.append(item)
        
        if not requested_items:
            return image_paths
        
        print(f"DEBUG: Requested items for images: {requested_items}")  # Debug log
        
        # Find relevant crops by checking all available crops dynamically
        relevant_crops = []
        combined_text = (user_query + " " + response_text).lower()
        
        # Check all crops from the data
        for crop_name in self.crop_data.keys():
            if crop_name.lower() in combined_text:
                relevant_crops.append(crop_name)
        
        # If no crop found in current context, try chat history
        if not relevant_crops and chat_history:
            for exchange in chat_history[-3:]:
                history_text = (exchange.get('user', '') + " " + exchange.get('assistant', '')).lower()
                for crop_name in self.crop_data.keys():
                    if crop_name.lower() in history_text and crop_name not in relevant_crops:
                        relevant_crops.append(crop_name)
        
        # If still no crop found, search all crops
        crops_to_search = relevant_crops if relevant_crops else list(self.crop_data.keys())
        
        # Search for the requested items in the crop data
        for crop in crops_to_search:
            if crop in self.crop_data:
                crop_info = self.crop_data[crop]
                
                for category_name, category_data in crop_info.items():
                    if isinstance(category_data, list):
                        for item in category_data:
                            if isinstance(item, dict) and 'image' in item:
                                # Check if this item is in the requested list
                                for requested_item in requested_items:
                                    item_name = item.get('name', '').strip()
                                    # More flexible matching - check exact match, partial match, and description match
                                    item_matches = False
                                    
                                    # Exact match (case insensitive)
                                    if item_name and item_name.lower() == requested_item.lower():
                                        item_matches = True
                                    # Partial match (requested item contains item name or vice versa)
                                    elif item_name and (requested_item.lower() in item_name.lower() or item_name.lower() in requested_item.lower()):
                                        item_matches = True
                                    # Description match
                                    elif requested_item.lower() in item.get('description', '').lower():
                                        item_matches = True
                                    
                                    if item_matches:
                                        image_url = convert_path_to_url(item['image'])
                                        if image_url not in [img['url'] for img in image_paths]:
                                            display_name = item_name if item_name else requested_item
                                            image_paths.append({
                                                'url': image_url,
                                                'name': display_name,
                                                'category': category_name,
                                                'crop': crop
                                            })
                                            print(f"DEBUG : Found image for '{requested_item}' -> '{display_name}' in {crop}/{category_name}")  # Debug log
                                            break
        
        return image_paths

    def clean_response_text(self, response_text):
        """Remove SHOW_IMAGES directive from response text"""
        import re
        # Handle the specific format: "SHOW_IMAGES: item1, item2, item3"
        # First try with square brackets
        cleaned_text = re.sub(r'SHOW_IMAGES\s*:\s*\[.*?\]', '', response_text, flags=re.IGNORECASE | re.DOTALL)
        # Then handle without brackets (comma-separated items)
        cleaned_text = re.sub(r'SHOW_IMAGES\s*:\s*[^"\n]*', '', cleaned_text, flags=re.IGNORECASE)
        # Also handle quoted items
        cleaned_text = re.sub(r'SHOW_IMAGES\s*:\s*"[^"]*"', '', cleaned_text, flags=re.IGNORECASE)
        # Clean up any remaining SHOW_IMAGES mentions
        cleaned_text = re.sub(r'SHOW_IMAGES[^\n]*', '', cleaned_text, flags=re.IGNORECASE)
        # Clean up any extra whitespace and newlines
        cleaned_text = re.sub(r'\s+', ' ', cleaned_text).strip()
        return cleaned_text

    def generate_prompt(self, user_query, context=None, language='hindi', chat_history=None):
        # Format chat history for context
        history_context = ""
        if chat_history and len(chat_history) > 0:
            history_context = "\n\nCHAT HISTORY (for context):\n"
            for i, exchange in enumerate(chat_history[-10:], 1):  # Use only last 10 exchanges
                history_context += f"{i}. User: {exchange['user']}\n   Assistant: {exchange['assistant'][:100]}...\n"
            history_context += "\nPlease consider this conversation history when responding to maintain context and continuity.\n"
        
        # Determine if we should greet (only for first message)
        should_greet = len(chat_history) == 0 if chat_history else True
        greeting_instruction = "Always start responses with a friendly greeting" if should_greet else "Do NOT greet the user, just provide the information directly"
        
        # Truly dynamic prompt - learns everything from JSON structure
        base_prompt = f"""You are a friendly and helpful agriculture assistant who provides information about crops. Act as a knowledgeable friend. Do not give a gender to yourself.

CRITICAL LANGUAGE INSTRUCTION: 
- You MUST respond in {language.upper()} ONLY
- ALL data from the JSON file is currently in Hindi/Devanagari script
- If user language is ENGLISH, you MUST translate ALL Hindi content to English
- If user language is HINDI, you can use the Hindi content as-is
- This includes translating: crop names, item names, descriptions, categories, and all agricultural terms
- NEVER mix languages in your response

JSON DATA STRUCTURE UNDERSTANDING:
The provided JSON data follows this structure:
{{
    "Crop_name": {{
        "Sub-section": [
            {{
                "name": "item_name",
                "description": "item_description", 
                "image": "item_image_path"
            }}
        ]
    }}
}}

YOU MUST ANALYZE THE ACTUAL JSON DATA to understand:
- What crops are available (top-level keys)
- What sub-sections each crop has (second-level keys) 
- What items are in each sub-section (array elements)
- Which items have images (items with "image" field)

DO NOT assume any specific category names - discover them dynamically from the JSON structure. Translate the data coming from the json file to user's language if it is already not in user's language.

Available crop data: {json.dumps(self.crop_data, ensure_ascii=False)}

TRANSLATION EXAMPLE:
If user asks about "मक्का के कीट" in English, respond like this:
"Maize Insects: The main insects affecting maize are Stem Borer, Aphid, and Armyworm. Which specific insect would you like to know about?"

NOT like this:
"मक्का के कीट: मुख्य कीट तनाबेधक, माहू और घाव बेधक हैं।"

INTERACTIVE CONVERSATION RULES:
1. {greeting_instruction}
2. CRITICAL RESPONSE LENGTH RULES:
   - KEEP RESPONSES UNDER 60 WORDS for general crop/sub-section questions
   - PROVIDE COMPREHENSIVE DETAILED INFORMATION when user asks about a specific item name
   - NO WORD LIMIT for specific item responses - include EVERYTHING: complete description, all available details from the JSON data
   - For specific items: Extract and present ALL data fields including name, description, and everything available
3. Follow this conversation pattern:
   - If user asks about a crop: Give 1 line about the crop, then ask which sub-section they want to know about (discover sub-sections from JSON)
   - If user asks about a sub-section: List only NAMES of items in that sub-section, then ask which specific item they want details about
   - If user asks about a specific item by name: This is a DETAILED RESPONSE - provide ALL information available in the JSON including complete description and everything available. Extract the entire "description" field completely.
   - If user doesn't cuts the conversation pattern, just respond to the user's question directly.
4. ITEM DETECTION: If the user query matches any item name from any sub-section, treat it as a specific item request and provide full details
5. Always encourage further interaction with questions (except for detailed item responses)
6. Always add one more question like the pattern "or do you want to know about anything else?" in the end of the response.
7. Dynamically discover available sub-sections from the JSON data structure for each crop
8. For any crop mentioned, check what sub-sections are available in the data and offer those options
9. Translate the data coming from the json file to user's language if it is already not in user's language.

FORMATTING RULES:
1. For listing multiple items:
   - List items as simple comma-separated names without repeating "Name:" or "नाम:" 
   - CORRECT: "Main items: item1, item2, item3. Which item details?" OR "मुख्य आइटम: आइटम1, आइटम2, आइटम3। किस आइटम के बारे में जानना चाहते हैं?"
   - WRONG: "Name: item1 Name: item2..." OR "नाम: आइटम1 नाम: आइटम2..."
2. For detailed item descriptions:
   - Use "**Item Name:**" format for the main heading only once. Replace the item name with the actual item name in the json file.
   - Add proper line breaks for readability
3. Never use bullet points or asterisks
4. Separate paragraphs with blank lines

CONTENT RULES:
1. You MUST base all of your answers strictly on the provided crop data.
2. If information is not available in the data, politely say so, DO NOT use any external knowledge
3. Analyze the JSON structure dynamically to understand what crops and sub-sections are available
4. Format the response clearly with proper line breaks
5. IMPORTANT: Use the chat history to maintain conversation context
6. CRITICAL TRANSLATION RULE: When user language is ENGLISH, translate ALL Hindi content to English: 
(Example:
   - Crop names: "मक्का" → "Maize", "धान" → "Rice", "गेहूँ" → "Wheat"
   - Item names: "तनाबेधक" → "Stem Borer", "माहू" → "Aphid", "भूमि की तैयारी" → "Land Preparation"
   - Descriptions: Translate the entire description text from Hindi to English
   - Maintain the same structure and formatting, just translate the content)
   - Translate the item name only when there is a possible translation for that word in English, otherwise transliterate the item name in English.
When user language is Hindi, translate category names from English to Hindi:
(
   - Category names: "Management" → "प्रबंधन", "Insects" → "कीट", "Diseases" → "रोग", "Weeds" → "खरपतवार", "Fertilizers" → "उर्वरक", "Varieties" → "फसल कि किस्में")
)


IMAGE DISPLAY INSTRUCTIONS (APPLIES TO BOTH LANGUAGES EQUALLY):
- Items that have an "image" field in the JSON have associated images
- If your response mentions specific items that have images, indicate which images should be displayed
- At the END of your response, add: "SHOW_IMAGES: item_name1, item_name2, item_name3" 
- For general/sub-section responses: Show maximum 3 images
- For specific item details: Show ALL available images for that item
- THIS WORKS THE SAME IN ENGLISH AND HINDI RESPONSES
- Even if the data is translated to user's language, you still need to show the images linked to that data
- CRITICAL: Always use the ORIGINAL Hindi item names in SHOW_IMAGES directive, even when responding in English
- The image matching system looks for the original Hindi names from the JSON data

CRITICAL RESTRICTIONS:
- NEVER mention file paths, URLs, or technical details like "./uploads/" or ".jpg"
- NEVER refer to image locations or file names in your main response text
- Focus only on agricultural content, not technical implementation details
- NEVER use words like "database, json, etc." in your response
- The SHOW_IMAGES section should be separate from your main response
- DO NOT hardcode any category names - discover everything from the JSON structure

{history_context}

Context (if any): {context if context else 'None'}
User Question: {user_query}"""

        return base_prompt

    def detect_language_change(self, query):
        """Detect if the user wants to change the language"""
        query_lower = query.lower()
        
        # Common Hindi language change patterns
        hindi_patterns = [
            "hindi", "हिंदी", "हिन्दी में", "हिंदी में बात", 
            "हिंदी में बोलो", "हिंदी में जवाब", "हिंदी में बताओ"
        ]
        
        # Common English language change patterns
        english_patterns = [
            "english", "speak in english", "talk in english", 
            "switch to english", "change to english", "reply in english",
            "answer in english"
        ]
        
        # Check for language change request
        if any(pattern in query_lower for pattern in hindi_patterns):
            return "hindi"
        elif any(pattern in query_lower for pattern in english_patterns):
            return "english"
        
        return None

    def generate_contextual_suggestion(self, language='hindi'):
        """
        Generate contextual crop suggestions based on current weather, climate, and month
        """
        try:
            # Get current weather and month information
            weather_data = self.weather_service.get_current_weather()
            month_info = self.weather_service.get_current_month_info()
            
            # Create context for Gemini to generate suggestions
            context_prompt = f"""
You are an agriculture expert. Based on the current weather and month information, suggest crops that are suitable for planting or growing right now.

CURRENT CONDITIONS:
- Month: {month_info['month_name_english']} ({month_info['month_name_hindi']})
- Temperature: {weather_data['temperature']}°C
- Humidity: {weather_data['humidity']}%
- Weather Condition: {weather_data['weather_condition']}
- Season: {weather_data.get('season', 'unknown')}

AVAILABLE CROPS IN DATABASE:
{list(self.crop_data.keys())}

TASK: Generate a friendly suggestion message that:
1. Mentions the current season/month/weather conditions
2. Suggests 2-3 crops that are ideal for the current conditions
3. Asks if the user wants to know about these crops or something else
4. Keep the message conversational and helpful
5. Respond in {language.upper()} language only

FORMAT: "Since it is [season/month] and [weather condition], it's a great time for [crop1], [crop2], [crop3]. Would you like to know about [crop1], [crop2], [crop3], or do you want to know about something else?"

IMPORTANT: Only suggest crops that are available in the database: {list(self.crop_data.keys())}
"""

            response = model.generate_content(context_prompt)
            return response.text.strip()
            
        except Exception as e:
            print(f"Error generating contextual suggestion: {e}")
            # Fallback suggestion
            if language == 'hindi':
                return "नमस्कार! मैं आपका कृषि सहायक हूं। आप किस फसल के बारे में जानना चाहते हैं?"
            else:
                return "Hello! I am your Agriculture Assistant. What crop would you like to know about?"

    def get_response(self, user_query, language='hindi', chat_history=None):
        try:
            # First check if this is a language change request
            new_language = self.detect_language_change(user_query)
            if new_language:
                if new_language == "hindi":
                    return {
                        "text": "ठीक है, अब मैं हिंदी में बात करूंगा।",
                        "images": []
                    }
                else:
                    return {
                        "text": "Alright, I will now converse in English.",
                        "images": []
                    }
            
            # Generate prompt and let Gemini handle all conversation flow dynamically
            prompt = self.generate_prompt(user_query, None, language, chat_history)
            
            # Generate response
            response = model.generate_content(prompt)
            response_text = response.text.strip()
            
            print(f"DEBUG: Raw response from Gemini: {response_text[:200]}...")  # Debug log
            
            # Extract relevant images
            image_paths = self.extract_image_paths_from_response(response_text, user_query, chat_history)
            
            print(f"DEBUG: Extracted {len(image_paths)} images")  # Debug log
            
            # Clean the response text for user display
            cleaned_response = self.clean_response_text(response_text)
            
            return {
                "text": cleaned_response,
                "images": image_paths
            }
            
        except Exception as e:
            error_message = f"Error: {str(e)}" if language == 'english' else f"त्रुटि: {str(e)}"
            return {
                "text": error_message,
                "images": []
            }
