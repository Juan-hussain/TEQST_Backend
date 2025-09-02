"""
Opus audio codec utilities for TEQST backend.

This module provides functionality for:
- Opus audio format detection
- Audio conversion between formats
- Metadata extraction
- Quality assessment
"""

import os
import wave
import tempfile
from pathlib import Path
from typing import Optional, Tuple, Dict, Any
import logging

try:
    import opuslib
    OPUS_AVAILABLE = True
except ImportError:
    OPUS_AVAILABLE = False
    logging.warning("opuslib not available, Opus support will be limited")

try:
    from pydub import AudioSegment
    PYDUB_AVAILABLE = True
except ImportError:
    PYDUB_AVAILABLE = False
    logging.warning("pydub not available, audio conversion will be limited")

logger = logging.getLogger(__name__)

class OpusAudioProcessor:
    """Handles Opus audio processing operations."""
    
    # Opus quality presets
    OPUS_PRESETS = {
        'low': {
            'bitrate': 16000,
            'sample_rate': 16000,
            'channels': 1,
            'frame_size': 20,  # ms
            'complexity': 3
        },
        'medium': {
            'bitrate': 32000,
            'sample_rate': 24000,
            'channels': 1,
            'frame_size': 20,  # ms
            'complexity': 6
        },
        'high': {
            'bitrate': 64000,
            'sample_rate': 48000,
            'channels': 1,
            'frame_size': 20,  # ms
            'complexity': 8
        }
    }
    
    def __init__(self, quality_preset: str = 'medium'):
        """
        Initialize the Opus processor.
        
        Args:
            quality_preset: Quality preset ('low', 'medium', 'high')
        """
        if not OPUS_AVAILABLE:
            raise RuntimeError("Opus support not available. Install opuslib package.")
        
        if quality_preset not in self.OPUS_PRESETS:
            raise ValueError(f"Invalid quality preset: {quality_preset}")
        
        self.quality_preset = quality_preset
        self.settings = self.OPUS_PRESETS[quality_preset]
        
        # Initialize Opus encoder
        self.encoder = opuslib.Encoder(
            fs=self.settings['sample_rate'],
            channels=self.settings['channels'],
            application=opuslib.APPLICATION_AUDIO
        )
        
        # Set encoder parameters
        self.encoder.bitrate = self.settings['bitrate']
        self.encoder.complexity = self.settings['complexity']
        
        logger.info(f"Opus processor initialized with {quality_preset} quality preset")
    
    def detect_audio_format(self, file_path: str) -> Dict[str, Any]:
        """
        Detect the format and properties of an audio file.
        
        Args:
            file_path: Path to the audio file
            
        Returns:
            Dictionary containing format information
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Audio file not found: {file_path}")
        
        file_info = {
            'path': file_path,
            'size': os.path.getsize(file_path),
            'extension': Path(file_path).suffix.lower(),
            'format': 'unknown',
            'sample_rate': None,
            'channels': None,
            'duration': None,
            'bitrate': None
        }
        
        try:
            if file_info['extension'] == '.opus':
                file_info['format'] = 'opus'
                file_info.update(self._extract_opus_info(file_path))
            elif file_info['extension'] == '.wav':
                file_info['format'] = 'wav'
                file_info.update(self._extract_wav_info(file_path))
            else:
                # Try to detect format using pydub
                if PYDUB_AVAILABLE:
                    file_info.update(self._extract_generic_info(file_path))
                
        except Exception as e:
            logger.error(f"Error detecting audio format for {file_path}: {e}")
            file_info['error'] = str(e)
        
        return file_info
    
    def _extract_opus_info(self, file_path: str) -> Dict[str, Any]:
        """Extract information from Opus file."""
        info = {}
        
        try:
            # Basic Opus file analysis
            with open(file_path, 'rb') as f:
                # Read Opus header (simplified)
                header = f.read(28)
                if header.startswith(b'OggS'):
                    info['container'] = 'ogg'
                    # Extract basic info from Ogg container
                    # This is a simplified implementation
                    info['sample_rate'] = 48000  # Default for Opus
                    info['channels'] = 1  # Default for speech
                    info['bitrate'] = self.settings['bitrate']
                    
                    # Estimate duration based on file size and bitrate
                    if info['bitrate']:
                        file_size = os.path.getsize(file_path)
                        info['duration'] = (file_size * 8) / (info['bitrate'] * 1000)
        except Exception as e:
            logger.warning(f"Could not extract Opus info: {e}")
        
        return info
    
    def _extract_wav_info(self, file_path: str) -> Dict[str, Any]:
        """Extract information from WAV file."""
        info = {}
        
        try:
            with wave.open(file_path, 'rb') as wav_file:
                info['sample_rate'] = wav_file.getframerate()
                info['channels'] = wav_file.getnchannels()
                info['duration'] = wav_file.getnframes() / wav_file.getframerate()
                
                # Calculate bitrate
                bits_per_sample = wav_file.getsampwidth() * 8
                info['bitrate'] = (info['sample_rate'] * info['channels'] * bits_per_sample) / 1000
        except Exception as e:
            logger.warning(f"Could not extract WAV info: {e}")
        
        return info
    
    def _extract_generic_info(self, file_path: str) -> Dict[str, Any]:
        """Extract information using pydub for other formats."""
        info = {}
        
        try:
            audio = AudioSegment.from_file(file_path)
            info['sample_rate'] = audio.frame_rate
            info['channels'] = audio.channels
            info['duration'] = len(audio) / 1000.0  # Convert to seconds
            
            # Estimate bitrate
            file_size = os.path.getsize(file_path)
            info['bitrate'] = (file_size * 8) / (info['duration'] * 1000)
        except Exception as e:
            logger.warning(f"Could not extract generic audio info: {e}")
        
        return info
    
    def convert_to_opus(self, input_path: str, output_path: str, 
                        quality_preset: Optional[str] = None) -> bool:
        """
        Convert audio file to Opus format.
        
        Args:
            input_path: Path to input audio file
            output_path: Path for output Opus file
            quality_preset: Quality preset to use (optional)
            
        Returns:
            True if conversion successful, False otherwise
        """
        if not PYDUB_AVAILABLE:
            logger.error("pydub not available for audio conversion")
            return False
        
        try:
            # Load audio using pydub
            audio = AudioSegment.from_file(input_path)
            
            # Apply quality preset if specified
            if quality_preset and quality_preset in self.OPUS_PRESETS:
                preset = self.OPUS_PRESETS[quality_preset]
                # Resample if needed
                if audio.frame_rate != preset['sample_rate']:
                    audio = audio.set_frame_rate(preset['sample_rate'])
                # Convert to mono if needed
                if audio.channels != preset['channels']:
                    audio = audio.set_channels(preset['channels'])
            
            # Export as Opus
            audio.export(output_path, format='opus', 
                        bitrate=f"{self.settings['bitrate']}k",
                        parameters=["-c:a", "libopus"])
            
            logger.info(f"Successfully converted {input_path} to {output_path}")
            return True
            
        except Exception as e:
            logger.error(f"Error converting {input_path} to Opus: {e}")
            return False
    
    def convert_to_wav(self, input_path: str, output_path: str,
                       sample_rate: Optional[int] = None,
                       channels: Optional[int] = None) -> bool:
        """
        Convert audio file to WAV format.
        
        Args:
            input_path: Path to input audio file
            output_path: Path for output WAV file
            sample_rate: Target sample rate (optional)
            channels: Target number of channels (optional)
            
        Returns:
            True if conversion successful, False otherwise
        """
        if not PYDUB_AVAILABLE:
            logger.error("pydub not available for audio conversion")
            return False
        
        try:
            # Load audio using pydub
            audio = AudioSegment.from_file(input_path)
            
            # Apply transformations if specified
            if sample_rate and audio.frame_rate != sample_rate:
                audio = audio.set_frame_rate(sample_rate)
            
            if channels and audio.channels != channels:
                audio = audio.set_channels(channels)
            
            # Export as WAV
            audio.export(output_path, format='wav')
            
            logger.info(f"Successfully converted {input_path} to {output_path}")
            return True
            
        except Exception as e:
            logger.error(f"Error converting {input_path} to WAV: {e}")
            return False
    
    def get_audio_quality_metrics(self, file_path: str) -> Dict[str, Any]:
        """
        Analyze audio quality and provide metrics.
        
        Args:
            file_path: Path to the audio file
            
        Returns:
            Dictionary containing quality metrics
        """
        metrics = {
            'file_path': file_path,
            'format_info': self.detect_audio_format(file_path),
            'quality_score': 0,
            'recommendations': []
        }
        
        try:
            format_info = metrics['format_info']
            
            # Calculate quality score based on various factors
            score = 0
            
            # Sample rate scoring
            if format_info.get('sample_rate'):
                sr = format_info['sample_rate']
                if sr >= 48000:
                    score += 30
                elif sr >= 24000:
                    score += 20
                elif sr >= 16000:
                    score += 10
            
            # Bitrate scoring
            if format_info.get('bitrate'):
                bitrate = format_info['bitrate']
                if bitrate >= 64:
                    score += 30
                elif bitrate >= 32:
                    score += 20
                elif bitrate >= 16:
                    score += 10
            
            # Format scoring
            if format_info.get('format') == 'opus':
                score += 20  # Opus is more efficient
            elif format_info.get('format') == 'wav':
                score += 10
            
            # Duration scoring (longer recordings get bonus)
            if format_info.get('duration'):
                duration = format_info['duration']
                if duration > 60:  # More than 1 minute
                    score += 10
                elif duration > 10:  # More than 10 seconds
                    score += 5
            
            metrics['quality_score'] = min(100, score)
            
            # Generate recommendations
            if format_info.get('sample_rate', 0) < 24000:
                metrics['recommendations'].append("Consider using higher sample rate for better quality")
            
            if format_info.get('format') != 'opus':
                metrics['recommendations'].append("Consider converting to Opus for better compression")
            
            if format_info.get('bitrate', 0) < 32:
                metrics['recommendations'].append("Consider using higher bitrate for better quality")
                
        except Exception as e:
            logger.error(f"Error analyzing audio quality: {e}")
            metrics['error'] = str(e)
        
        return metrics
    
    def cleanup(self):
        """Clean up resources."""
        if hasattr(self, 'encoder'):
            del self.encoder


def is_opus_file(file_path: str) -> bool:
    """
    Check if a file is an Opus audio file.
    
    Args:
        file_path: Path to the file
        
    Returns:
        True if file is Opus, False otherwise
    """
    try:
        with open(file_path, 'rb') as f:
            header = f.read(28)
            return header.startswith(b'OggS')
    except Exception:
        return False


def get_opus_version() -> str:
    """
    Get the version of the Opus library.
    
    Returns:
        Opus library version string
    """
    if OPUS_AVAILABLE:
        try:
            return opuslib.__version__
        except AttributeError:
            return "Unknown"
    return "Not available"


def create_opus_processor(quality_preset: str = 'medium') -> Optional[OpusAudioProcessor]:
    """
    Create an Opus audio processor with the specified quality preset.
    
    Args:
        quality_preset: Quality preset ('low', 'medium', 'high')
        
    Returns:
        OpusAudioProcessor instance or None if not available
    """
    try:
        return OpusAudioProcessor(quality_preset)
    except Exception as e:
        logger.error(f"Failed to create Opus processor: {e}")
        return None

