from django.urls import path
from . import views
from . import opus_views

urlpatterns = [
    path('spk/textrecordings/', views.TextRecordingView.as_view(), name='textrecs'),
    path('spk/sentencerecordings/', views.SentenceRecordingCreateView.as_view(), name='sentencerecs-create'),
    path('spk/sentencerecordings/<int:rec>/', views.SentenceRecordingUpdateView.as_view(), name='sentencerecs-detail'),
    path('spk/sentencerecordings/<int:tr_id>/<int:index>/', views.SentenceRecordingRetrieveUpdateView.as_view(), name='sentencerecs-retrieveupdate'),
    
    # Opus audio processing endpoints
    path('opus/convert/', opus_views.OpusAudioConversionView.as_view(), name='opus-convert'),
    path('opus/analyze/', opus_views.OpusAudioAnalysisView.as_view(), name='opus-analyze'),
    path('opus/info/', opus_views.opus_system_info, name='opus-info'),
    path('opus/batch-convert/', opus_views.opus_batch_convert, name='opus-batch-convert'),
]