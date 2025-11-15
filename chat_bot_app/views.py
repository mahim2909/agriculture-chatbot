from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from .chatbot import CropChatBot
import google.generativeai as genai
import tempfile
import os
import speech_recognition as sr
from pydub import AudioSegment
import io
import logging

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

chatbot = CropChatBot()

def chat_view(request):
    if request.method == 'GET':
        # Reset session on new page load
        request.session['message_count'] = 0
        request.session['language'] = None
        request.session['chat_history'] = []  # Initialize empty chat history
        return render(request, 'chat_bot_app/chat.html')
    
    elif request.method == 'POST':
        # Check if this is a language selection request
        language_selection = request.POST.get('language_selection', None)
        if language_selection:
            request.session['language'] = language_selection
            
            # Generate contextual suggestion after language selection
            contextual_suggestion = chatbot.generate_contextual_suggestion(language_selection)
            # Provide available crops/fruits dynamically from JSON keys
            available_crops = list(chatbot.crop_data.keys())
            
            return JsonResponse({
                'success': True, 
                'contextual_suggestion': contextual_suggestion,
                'available_crops': available_crops
            })
        
        # Check if this is the initial greeting request
        is_greeting = request.POST.get('greeting', False)
        # Get the message count from session
        message_count = request.session.get('message_count', 0)
        
        # Check if message limit is reached
        if message_count >= 10:
            return JsonResponse({
                'error': 'You have reached the maximum number of messages for this session. Please refresh the page to start a new session.'
            })
        
        # Handle greeting separately (this is now handled by frontend)
        if is_greeting:
            # Get available crops dynamically from the chatbot data
            available_crops = list(chatbot.crop_data.keys())
            crops_list = ", ".join(available_crops)
            
            greeting_message = f"""नमस्कार! मैं आपका कृषि सहायक हूं। {crops_list} के बारे में पूछें।
            
Hello! I am your Agriculture Assistant. Ask about {crops_list}."""
            return JsonResponse({'reply': greeting_message})

        # Get the user's question
        question = request.POST.get('question', '')
        if not question:
            return JsonResponse({'error': 'No question provided'})
        
        # Get user's language preference and chat history from session
        user_language = request.session.get('language', 'hindi')
        chat_history = request.session.get('chat_history', [])
        
        # Get response from chatbot with language preference and chat history
        response_data = chatbot.get_response(question, user_language, chat_history)
        
        # Handle both old string format and new dict format for backward compatibility
        if isinstance(response_data, str):
            response_text = response_data
            images = []
        else:
            response_text = response_data.get('text', '')
            images = response_data.get('images', [])
        
        # Check if response indicates a language change
        if "I will now converse in English" in response_text:
            request.session['language'] = 'english'
        elif "अब मैं हिंदी में बात करूंगा" in response_text:
            request.session['language'] = 'hindi'
        
        # Add current exchange to chat history
        chat_history.append({
            'user': question,
            'assistant': response_text,
            'timestamp': str(message_count + 1)
        })
        
        # Store updated chat history in session (keep only last 10 exchanges to avoid too much context)
        if len(chat_history) > 10:
            chat_history = chat_history[-10:]
        request.session['chat_history'] = chat_history
        
        # Only increment count for non-greeting messages
        message_count += 1
        request.session['message_count'] = message_count
        
        return JsonResponse({
            'reply': response_text,
            'images': images
        })

import speech_recognition as sr
from pydub import AudioSegment
import io

def process_voice(request):
    if request.method == 'POST' and request.FILES.get('audio'):
        tmp_file = None
        wav_file = None
        
        try:
            audio_file = request.FILES['audio']
            
            # Create temporary files with explicit names
            tmp_file = tempfile.NamedTemporaryFile(suffix='.webm', delete=False)
            wav_file = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
            
            # Get the file paths
            tmp_file_path = tmp_file.name
            wav_path = wav_file.name
            
            # Write audio data to temporary file
            for chunk in audio_file.chunks():
                tmp_file.write(chunk)
            tmp_file.flush()
            os.fsync(tmp_file.fileno())
            tmp_file.close()
            
            print(f"Debug: WebM file created at {tmp_file_path}")
            print(f"Debug: WebM file size: {os.path.getsize(tmp_file_path)}")
            
            # Convert WebM to WAV
            audio = AudioSegment.from_file(tmp_file_path, format="webm")
            audio.export(wav_path, format="wav")
            
            # Use speech recognition
            r = sr.Recognizer()
            with sr.AudioFile(wav_path) as source:
                audio_data = r.record(source)
                # Convert speech to text
                text = r.recognize_google(audio_data)
            
            # Get user's language preference and chat history from session
            user_language = request.session.get('language', 'hindi')
            chat_history = request.session.get('chat_history', [])
            
            # Get response from chatbot with language and history context
            chatbot_response = chatbot.get_response(text, user_language, chat_history)
            
            # Handle both string and dict responses
            if isinstance(chatbot_response, str):
                response_text = chatbot_response
                images = []
            else:
                response_text = chatbot_response.get('text', '')
                images = chatbot_response.get('images', [])
            
            # Update chat history with this exchange
            chat_history.append({
                'user': text,
                'assistant': response_text,
                'timestamp': str(len(chat_history) + 1)
            })
            
            # Keep only last 10 exchanges
            if len(chat_history) > 10:
                chat_history = chat_history[-10:]
            request.session['chat_history'] = chat_history
            
            # Update language if response indicates a change
            if "I will now converse in English" in response_text:
                request.session['language'] = 'english'
            elif "अब मैं हिंदी में बात करूंगा" in response_text:
                request.session['language'] = 'hindi'
            
            # Format the response
            response = {
                'reply': response_text,
                'images': images,  # This will include any images from the chatbot response
                'transcribed_text': text  # Include the transcribed text
            }
            
            # Log the response for debugging
            logger.debug(f"Voice response: {response}")
            
            return JsonResponse(response)
            
        except sr.UnknownValueError:
            return JsonResponse({'error': 'Could not understand the audio. Please try again.'})
        except sr.RequestError as e:
            return JsonResponse({'error': f'Could not process audio: {str(e)}'})
        except Exception as e:
            logger.error(f"Error in process_voice: {str(e)}", exc_info=True)
            return JsonResponse({'error': f'Error processing voice message: {str(e)}'})
        finally:
            # Clean up temporary files
            try:
                if tmp_file and os.path.exists(tmp_file.name):
                    os.unlink(tmp_file.name)
                    logger.debug(f"Removed WebM file: {tmp_file.name}")
            except Exception as e:
                logger.error(f"Error removing temporary WebM file: {e}")
            
            try:
                if wav_file and os.path.exists(wav_file.name):
                    os.unlink(wav_file.name)
                    logger.debug(f"Removed WAV file: {wav_file.name}")
            except Exception as e:
                logger.error(f"Error removing temporary WAV file: {e}")
                
            try:
                if 'tmp_file' in locals() and tmp_file:
                    tmp_file.close()
                if 'wav_file' in locals() and wav_file:
                    wav_file.close()
            except Exception as e:
                logger.error(f"Error closing temporary files: {e}")

    return JsonResponse({'error': 'Invalid request'}, status=400)
