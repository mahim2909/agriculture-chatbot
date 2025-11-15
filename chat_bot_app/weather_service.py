import json
from datetime import datetime
import google.generativeai as genai

class WeatherService:
    def __init__(self):
        # Use Gemini API for weather information
        self.api_key = "AIzaSyBilto_r5gM_gzk0pQAHHE8oz2ih8ZxMn4"
        genai.configure(api_key=self.api_key)
        self.model = genai.GenerativeModel("gemini-2.5-flash")
        
    def get_current_weather(self, city="Raipur", country_code="IN"):
        """
        Get current weather data using Gemini AI (no mock fallback)
        Default to Raipur, India for Indian agriculture context
        """
        try:
            def map_month_to_india_season(month: int) -> str:
                # India-centric season mapping
                # Dec-Feb: winter, Mar-May: summer, Jun-Sep: monsoon, Oct-Nov: post_monsoon
                if month in (12, 1, 2):
                    return 'winter'
                if month in (3, 4, 5):
                    return 'summer'
                if month in (6, 7, 8, 9):
                    return 'monsoon'
                return 'post_monsoon'  # Oct, Nov

            # Use Gemini to get weather information
            weather_prompt = f"""
You are a weather information provider. Provide current-like weather for {city}, {country_code}.

STRICT OUTPUT: Return ONLY raw JSON object without any surrounding text or code fences. Keys and types:
{{
  "temperature": number,             // Celsius, integer or float
  "humidity": number,                // percentage (0-100)
  "weather_condition": string,       // e.g., Clear, Rain, Clouds
  "description": string,             // brief description
  "city": "{city}",
  "country": "{country_code}",
  "season": string                   // e.g., winter, summer, monsoon, post_monsoon
}}

Constraints:
- Do NOT include markdown or code fences
- Do NOT include any additional text
"""

            response = self.model.generate_content(weather_prompt)
            weather_text = response.text.strip()

            def try_parse_json(text: str):
                # Remove code fences if present
                cleaned = text
                if cleaned.startswith('```json'):
                    cleaned = cleaned[7:]
                cleaned = cleaned.strip('`').strip()
                # First attempt direct parse
                try:
                    return json.loads(cleaned)
                except Exception:
                    pass
                # Try to extract the first JSON object substring
                import re
                match = re.search(r"\{[\s\S]*\}", cleaned)
                if match:
                    candidate = match.group(0)
                    try:
                        return json.loads(candidate)
                    except Exception:
                        return None
                return None

            weather_data = try_parse_json(weather_text)

            # Retry once with an even stricter prompt if parsing failed
            if weather_data is None:
                retry_prompt = f"Return ONLY this JSON (no markdown): {{\n  \"temperature\": number, \n  \"humidity\": number, \n  \"weather_condition\": string, \n  \"description\": string, \n  \"city\": \"{city}\", \n  \"country\": \"{country_code}\", \n  \"season\": string\n}} for current-like weather in {city}, {country_code}."
                retry_response = self.model.generate_content(retry_prompt)
                weather_data = try_parse_json(retry_response.text.strip())

            # If still not parsable, return unknowns (no mock)
            if weather_data is None:
                return {
                    'temperature': None,
                    'humidity': None,
                    'weather_condition': 'Unknown',
                    'description': 'unavailable',
                    'city': city,
                    'country': country_code,
                    'season': 'unknown'
                }

            # Ensure required keys exist; if missing, fill with unknowns
            required_fields = ['temperature', 'humidity', 'weather_condition', 'description', 'city', 'country', 'season']
            for key in required_fields:
                if key not in weather_data:
                    weather_data[key] = None if key in ['temperature', 'humidity'] else ('unknown' if key == 'season' else '')

            # Override/align season deterministically by current month for India
            current_month = datetime.now().month
            canonical_season = map_month_to_india_season(current_month)
            weather_data['season'] = canonical_season

            return weather_data
                
        except Exception as e:
            print(f"Gemini weather API error: {e}")
            return {
                'temperature': None,
                'humidity': None,
                'weather_condition': 'Unknown',
                'description': 'unavailable',
                'city': city,
                'country': country_code,
                'season': 'unknown'
            }
    
    def get_mock_weather_data(self):
        """Deprecated: No longer used (kept for backward compatibility)."""
        return {
            'temperature': None,
            'humidity': None,
            'weather_condition': 'Unknown',
            'description': 'unavailable',
            'city': 'Raipur',
            'country': 'IN',
            'season': 'unknown'
        }
    
    def get_current_month_info(self):
        """Get current month information"""
        current_month = datetime.now().month
        month_names = {
            1: "January", 2: "February", 3: "March", 4: "April",
            5: "May", 6: "June", 7: "July", 8: "August",
            9: "September", 10: "October", 11: "November", 12: "December"
        }
        
        month_names_hindi = {
            1: "जनवरी", 2: "फरवरी", 3: "मार्च", 4: "अप्रैल",
            5: "मई", 6: "जून", 7: "जुलाई", 8: "अगस्त",
            9: "सितंबर", 10: "अक्टूबर", 11: "नवंबर", 12: "दिसंबर"
        }
        
        return {
            'month_number': current_month,
            'month_name_english': month_names[current_month],
            'month_name_hindi': month_names_hindi[current_month]
        }
