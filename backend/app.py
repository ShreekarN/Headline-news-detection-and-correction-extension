from flask import Flask, request, jsonify
from flask_cors import CORS
import logging
import traceback
from models.text_model import check_and_rewrite_headline
from models.image_detector import analyze_images

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

@app.route('/analyze', methods=['POST'])
def analyze():
    try:
        data = request.get_json(force=True) or {}
    except Exception:
        return jsonify({'error': 'invalid json payload'}), 400

    title = data.get('title', '') or ''
    content = data.get('paragraphs', '') or ''
    images = data.get('image_urls') or data.get('images') or []
    page_url = data.get('page_url') or data.get('url') or ''

    if not title and not content:
        return jsonify({'error': 'no title or content provided'}), 400

    try:
        text_report = check_and_rewrite_headline(title, content)
    except Exception as e:
        logger.exception('Text model failed')
        text_report = {"error": "text model failed", "message": str(e)}

    image_report = []
    if images:
        try:
            image_report = analyze_images(images, try_fetch=True, page_url=page_url)
        except Exception as e:
            logger.exception('Image analysis failed')
            image_report = [{'image': None, 'status': 'error', 'reasons': [f'Image analysis failed: {str(e)}']}]

    return jsonify({'text_report': text_report, 'image_report': image_report})

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000, debug=True)
