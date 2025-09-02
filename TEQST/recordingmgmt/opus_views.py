"""
Opus audio processing views for TEQST backend.

This module provides API endpoints for:
- Audio format conversion
- Quality analysis
- Metadata extraction
- Opus-specific operations
"""

from rest_framework import generics, status, response
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser
from django.http import JsonResponse
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.conf import settings
import os
import tempfile
import logging

from . import models
from .opus_utils import (
    OpusAudioProcessor, 
    create_opus_processor, 
    is_opus_file,
    get_opus_version
)

logger = logging.getLogger(__name__)


class OpusAudioConversionView(generics.CreateAPIView):
    """
    Convert audio files to Opus format.
    
    POST /api/opus/convert/
    """
    parser_classes = (MultiPartParser, FormParser)
    permission_classes = [IsAuthenticated]
    
    def post(self, request, *args, **kwargs):
        try:
            # Get uploaded file
            audio_file = request.FILES.get('audio_file')
            if not audio_file:
                return response.Response(
                    {'error': 'No audio file provided'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Get quality preset
            quality_preset = request.data.get('quality', 'medium')
            if quality_preset not in ['low', 'medium', 'high']:
                quality_preset = 'medium'
            
            # Create temporary files
            with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(audio_file.name)[1]) as temp_input:
                for chunk in audio_file.chunks():
                    temp_input.write(chunk)
                temp_input_path = temp_input.name
            
            temp_output_path = temp_input_path.replace(os.path.splitext(temp_input_path)[1], '.opus')
            
            try:
                # Convert to Opus
                processor = create_opus_processor(quality_preset)
                if not processor:
                    return response.Response(
                        {'error': 'Opus processor not available'}, 
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR
                    )
                
                success = processor.convert_to_opus(temp_input_path, temp_output_path, quality_preset)
                
                if success and os.path.exists(temp_output_path):
                    # Read the converted file
                    with open(temp_output_path, 'rb') as f:
                        opus_data = f.read()
                    
                    # Create response with converted file
                    response_data = {
                        'message': 'Audio converted successfully',
                        'original_format': os.path.splitext(audio_file.name)[1][1:],
                        'converted_format': 'opus',
                        'quality_preset': quality_preset,
                        'original_size': audio_file.size,
                        'converted_size': len(opus_data),
                        'compression_ratio': round(audio_file.size / len(opus_data), 2)
                    }
                    
                    # Add file as attachment
                    response_obj = response.Response(response_data, status=status.HTTP_200_OK)
                    response_obj['Content-Disposition'] = f'attachment; filename="converted.opus"'
                    response_obj['Content-Type'] = 'audio/opus'
                    response_obj['Content-Length'] = str(len(opus_data))
                    
                    # Write file content to response
                    response_obj.content = opus_data
                    return response_obj
                else:
                    return response.Response(
                        {'error': 'Failed to convert audio'}, 
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR
                    )
                    
            finally:
                # Clean up temporary files
                processor.cleanup()
                if os.path.exists(temp_input_path):
                    os.unlink(temp_input_path)
                if os.path.exists(temp_output_path):
                    os.unlink(temp_output_path)
                    
        except Exception as e:
            logger.error(f"Error in Opus conversion: {e}")
            return response.Response(
                {'error': f'Conversion failed: {str(e)}'}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class OpusAudioAnalysisView(generics.CreateAPIView):
    """
    Analyze audio file quality and provide recommendations.
    
    POST /api/opus/analyze/
    """
    parser_classes = (MultiPartParser, FormParser)
    permission_classes = [IsAuthenticated]
    
    def post(self, request, *args, **kwargs):
        try:
            # Get uploaded file
            audio_file = request.FILES.get('audio_file')
            if not audio_file:
                return response.Response(
                    {'error': 'No audio file provided'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Create temporary file
            with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(audio_file.name)[1]) as temp_file:
                for chunk in audio_file.chunks():
                    temp_file.write(chunk)
                temp_file_path = temp_file.name
            
            try:
                # Analyze audio quality
                processor = create_opus_processor('medium')
                if not processor:
                    return response.Response(
                        {'error': 'Opus processor not available'}, 
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR
                    )
                
                metrics = processor.get_audio_quality_metrics(temp_file_path)
                
                # Clean up processor
                processor.cleanup()
                
                return response.Response(metrics, status=status.HTTP_200_OK)
                
            finally:
                # Clean up temporary file
                if os.path.exists(temp_file_path):
                    os.unlink(temp_file_path)
                    
        except Exception as e:
            logger.error(f"Error in Opus analysis: {e}")
            return response.Response(
                {'error': f'Analysis failed: {str(e)}'}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def opus_system_info(request):
    """
    Get Opus system information and capabilities.
    
    GET /api/opus/info/
    """
    try:
        info = {
            'opus_version': get_opus_version(),
            'opus_available': create_opus_processor() is not None,
            'supported_formats': ['wav', 'opus'],
            'quality_presets': ['low', 'medium', 'high'],
            'default_quality': 'medium'
        }
        
        # Add processor details if available
        processor = create_opus_processor()
        if processor:
            info['processor_settings'] = processor.settings
            info['opus_presets'] = processor.OPUS_PRESETS
            processor.cleanup()
        
        return JsonResponse(info)
        
    except Exception as e:
        logger.error(f"Error getting Opus system info: {e}")
        return JsonResponse({'error': str(e)}, status=500)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def opus_batch_convert(request):
    """
    Convert multiple audio files to Opus format.
    
    POST /api/opus/batch-convert/
    """
    try:
        # Get uploaded files
        audio_files = request.FILES.getlist('audio_files')
        if not audio_files:
            return response.Response(
                {'error': 'No audio files provided'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get quality preset
        quality_preset = request.data.get('quality', 'medium')
        if quality_preset not in ['low', 'medium', 'high']:
            quality_preset = 'medium'
        
        results = []
        processor = create_opus_processor(quality_preset)
        
        if not processor:
            return response.Response(
                {'error': 'Opus processor not available'}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
        try:
            for audio_file in audio_files:
                result = {
                    'filename': audio_file.name,
                    'status': 'pending',
                    'error': None
                }
                
                try:
                    # Create temporary files
                    with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(audio_file.name)[1]) as temp_input:
                        for chunk in audio_file.chunks():
                            temp_input.write(chunk)
                        temp_input_path = temp_input.name
                    
                    temp_output_path = temp_input_path.replace(os.path.splitext(temp_input_path)[1], '.opus')
                    
                    try:
                        # Convert to Opus
                        success = processor.convert_to_opus(temp_input_path, temp_output_path, quality_preset)
                        
                        if success and os.path.exists(temp_output_path):
                            result['status'] = 'success'
                            result['original_size'] = audio_file.size
                            result['converted_size'] = os.path.getsize(temp_output_path)
                            result['compression_ratio'] = round(audio_file.size / os.path.getsize(temp_output_path), 2)
                        else:
                            result['status'] = 'failed'
                            result['error'] = 'Conversion failed'
                            
                    finally:
                        # Clean up temporary files
                        if os.path.exists(temp_input_path):
                            os.unlink(temp_input_path)
                        if os.path.exists(temp_output_path):
                            os.unlink(temp_output_path)
                            
                except Exception as e:
                    result['status'] = 'failed'
                    result['error'] = str(e)
                
                results.append(result)
            
            return response.Response({
                'message': 'Batch conversion completed',
                'quality_preset': quality_preset,
                'results': results
            }, status=status.HTTP_200_OK)
            
        finally:
            processor.cleanup()
            
    except Exception as e:
        logger.error(f"Error in Opus batch conversion: {e}")
        return response.Response(
            {'error': f'Batch conversion failed: {str(e)}'}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

