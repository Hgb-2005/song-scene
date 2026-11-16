"""Composition rules shared by persistence and FFmpeg rendering (browser twin: composition.mjs)."""
from .store import AppError, number


def caption_settings(value=None):
    value = {} if value is None else value
    if not isinstance(value, dict) or not isinstance(value.get('enabled', True), bool):
        raise AppError('字幕设置格式不正确')
    return {'enabled': value.get('enabled', True), 'size': number(value.get('size', 4.7), 3, 8),
            'bottom': number(value.get('bottom', 10), 5, 85)}


def visual_filter(scene, width, height):
    x=number(scene.get('cropX', .5), 0, 1)
    y=number(scene.get('cropY', .5), 0, 1)
    return (f'scale={width}:{height}:force_original_aspect_ratio=increase,'
            f'crop={width}:{height}:x=(iw-ow)*{x}:y=(ih-oh)*{y},'
            'setsar=1,fps=30,format=yuv420p')
