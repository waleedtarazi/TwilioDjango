import json
from channels.generic.websocket import AsyncWebsocketConsumer
import websockets
import asyncio
from django.conf import settings

class MediaStreamConsumer(AsyncWebsocketConsumer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.openai_ws = None
        self.stream_sid = None
        self.response_start_timestamp_twilio = None
        self.latest_media_timestamp = 0
        self.last_assistant_item = None
        self.mark_queue = []

    async def connect(self):
        await self.accept()
        self.openai_ws = await websockets.connect(
            'wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-10-01',
            extra_headers={
                'Authorization': f'Bearer {settings.OPENAI_API_KEY}',
                'OpenAI-Beta': 'realtime=v1',
            }
        )
        await send_session_update(self.openai_ws)
        await send_initial_conversation_item(self.openai_ws)
        self.openai_task = asyncio.create_task(self.receive_from_openai())

    async def disconnect(self, close_code):
        if hasattr(self, 'openai_ws') and self.openai_ws:
            await self.openai_ws.close()
        if hasattr(self, 'openai_task'):
            self.openai_task.cancel()

    async def receive(self, text_data):
        message = json.loads(text_data)
        if message['event'] == 'media' and self.openai_ws.open:
            self.latest_media_timestamp = int(message['media']['timestamp'])
            audio_append = {
                'type': 'input_audio_buffer.append',
                'audio': message['media']['payload']
            }
            await self.openai_ws.send(json.dumps(audio_append))
        elif message['event'] == 'start':
            self.stream_sid = message['start']['streamSid']
            self.response_start_timestamp_twilio = None
            self.latest_media_timestamp = 0
            self.last_assistant_item = None
        elif message['event'] == 'mark':
            if self.mark_queue:
                self.mark_queue.pop(0)

    async def receive_from_openai(self):
        try:
            async for message in self.openai_ws:
                data = json.loads(message)
                if data['type'] == 'response.audio.delta':
                    audio_delta = data['delta']
                    await self.send(text_data=json.dumps({
                        'event': 'media',
                        'streamSid': self.stream_sid,
                        'media': {'payload': audio_delta},
                    }))
                elif data['type'] == 'input_audio_buffer.speech_started':
                    await handle_speech_started_event(self, self.openai_ws)
        except Exception as e:
            print(f"Error in receive_from_openai: {e}")
            
            

async def send_session_update(openai_ws):
    session_update = {
        'type': 'session.update',
        'session': {
            'turn_detection': {'type': 'server_vad'},
            'input_audio_format': 'g711_ulaw',
            'output_audio_format': 'g711_ulaw',
            'voice': settings.VOICE,
            'instructions': settings.SYSTEM_MESSAGE,
            'modalities': ['text', 'audio'],
            'temperature': 0.8,
        }
    }
    await openai_ws.send(json.dumps(session_update))

async def send_initial_conversation_item(openai_ws):
    initial_conversation_item = {
        'type': 'conversation.item.create',
        'item': {
            'type': 'message',
            'role': 'user',
            'content': [
                {
                    'type': 'input_text',
                    'text': "Greet the user with 'Hello there! I am an AI voice assistant that will help you with any questions you may have. Please ask me anything you want to know.'"
                }
            ]
        }
    }
    await openai_ws.send(json.dumps(initial_conversation_item))
    await openai_ws.send(json.dumps({'type': 'response.create'}))



async def handle_speech_started_event(consumer, openai_ws):
    if consumer.mark_queue and consumer.response_start_timestamp_twilio is not None:
        elapsed_time = consumer.latest_media_timestamp - consumer.response_start_timestamp_twilio
        if consumer.last_assistant_item:
            truncate_event = {
                'type': 'conversation.item.truncate',
                'item_id': consumer.last_assistant_item,
                'content_index': 0,
                'audio_end_ms': elapsed_time
            }
            await openai_ws.send(json.dumps(truncate_event))
        await consumer.send(text_data=json.dumps({
            'event': 'clear',
            'streamSid': consumer.stream_sid
        }))
        consumer.mark_queue.clear()
        consumer.last_assistant_item = None
        consumer.response_start_timestamp_twilio = None
