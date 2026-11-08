"""Original film-gate approximation from the supplied stills; opt-in only."""
from PIL import Image, ImageDraw, ImageFilter


def create_gate(path):
    gate = Image.new('RGBA', (1920, 1080))
    draw = ImageDraw.Draw(gate)
    draw.rounded_rectangle((-44, 390, 96, 706), radius=28,
                           outline=(255, 40, 25, 150), width=5)
    glow = gate.filter(ImageFilter.GaussianBlur(9))
    gate = Image.alpha_composite(glow, gate)
    ImageDraw.Draw(gate).rounded_rectangle((-44, 390, 96, 706), radius=28,
                                           outline=(255, 95, 60, 210), width=2)
    gate.save(path)


def normalize_filter(fit):
    if fit == 'square':
        sizing = ('scale=1080:1080:force_original_aspect_ratio=increase:force_divisible_by=2,'
                  'crop=1080:1080,pad=1920:1080:420:0:color=black')
    elif fit == 'contain':
        sizing = ('scale=1920:1080:force_original_aspect_ratio=decrease,'
                  'pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=black')
    else:
        sizing = 'scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080'
    return sizing + ',setsar=1,fps=30,format=yuv420p,setpts=PTS-STARTPTS'


def filters(spec, root):
    normal = normalize_filter(spec.get('video_fit', 'cover'))
    if spec.get('film_overlay', 'none') == 'none':
        return [], ['-map', '0:v:0', '-vf', normal]
    path = root / 'film-gate.png'
    create_gate(path)
    graph = (f'[0:v:0]{normal},noise=alls=3:allf=t+u:all_seed=8[film];'
             '[film][1:v:0]overlay=0:0:format=auto,format=yuv420p[v]')
    return ['-i', str(path)], ['-filter_complex', graph, '-map', '[v]']
