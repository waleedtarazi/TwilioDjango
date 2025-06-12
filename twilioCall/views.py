from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from twilio.twiml.voice_response import VoiceResponse, Connect, Stream

@csrf_exempt
def incoming_call(request):
    response = VoiceResponse()
    connect = Connect()
    stream = Stream(url=f'wss://{request.get_host()}/twilio-stream')
    connect.append(stream)
    response.append(connect)
    return HttpResponse(str(response), content_type='text/xml')