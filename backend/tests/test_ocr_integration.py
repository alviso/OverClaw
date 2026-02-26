"""
Test Suite for Tesseract OCR Integration
Tests extract_text_ocr(), _analyze_image(), analyze_and_store_screen(), and agent.py OCR processing

The OCR integration aims to extract pixel-perfect text from screen captures to avoid 
misreads like 'ext_mikova@mattoni.cz' being read as 'ext_mkoval@mattoni.cz'
"""
import pytest
import os
import sys
import tempfile
from PIL import Image, ImageDraw, ImageFont

# Add backend to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Test configuration
BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Use a reliable TTF font for generating test images
FONT_PATH = '/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf'


class TestTesseractInstallation:
    """Test that Tesseract OCR binary is installed and accessible"""
    
    def test_tesseract_binary_exists(self):
        """Tesseract binary should be installed at /usr/bin/tesseract"""
        assert os.path.exists('/usr/bin/tesseract'), "Tesseract binary not found at /usr/bin/tesseract"
        print("✓ Tesseract binary exists at /usr/bin/tesseract")
    
    def test_tesseract_version(self):
        """Tesseract should be version 5.x"""
        import subprocess
        result = subprocess.run(['tesseract', '--version'], capture_output=True, text=True)
        version_line = result.stdout.split('\n')[0]
        assert 'tesseract' in version_line.lower(), f"Unexpected version output: {version_line}"
        assert '5.' in version_line, f"Expected Tesseract 5.x, got: {version_line}"
        print(f"✓ Tesseract version: {version_line}")
    
    def test_pytesseract_import(self):
        """pytesseract should be importable"""
        import pytesseract
        assert pytesseract is not None
        print("✓ pytesseract imported successfully")
    
    def test_pillow_import(self):
        """Pillow should be importable with Image, ImageDraw, ImageFont"""
        from PIL import Image, ImageDraw, ImageFont
        assert Image is not None
        assert ImageDraw is not None
        assert ImageFont is not None
        print("✓ Pillow (PIL) imported successfully")


class TestExtractTextOCR:
    """Test extract_text_ocr() function from screen_memory.py"""
    
    @pytest.fixture
    def sample_text_image(self, tmp_path):
        """Create a sample PNG image with clear text for OCR testing"""
        # Create a white background image with black text
        img = Image.new('RGB', (800, 200), color='white')
        draw = ImageDraw.Draw(img)
        
        # Use a clear font for better OCR accuracy
        try:
            font = ImageFont.truetype(FONT_PATH, 32)
        except:
            font = ImageFont.load_default()
        
        # The exact text that was misread in the original bug report
        test_text = "ext_mikova@mattoni.cz"
        draw.text((50, 50), test_text, fill='black', font=font)
        draw.text((50, 100), "Contact: John Doe", fill='black', font=font)
        draw.text((50, 150), "ID: 12345678", fill='black', font=font)
        
        # Save to temp file
        img_path = tmp_path / "test_ocr_image.png"
        img.save(str(img_path))
        return str(img_path)
    
    @pytest.fixture
    def email_focused_image(self, tmp_path):
        """Create an image specifically with email addresses to test OCR accuracy"""
        img = Image.new('RGB', (600, 300), color='white')
        draw = ImageDraw.Draw(img)
        
        try:
            font = ImageFont.truetype(FONT_PATH, 28)
        except:
            font = ImageFont.load_default()
        
        # Multiple email addresses to test
        emails = [
            "ext_mikova@mattoni.cz",
            "john.smith@example.com",
            "admin_user123@domain.org"
        ]
        
        y = 30
        for email in emails:
            draw.text((30, y), email, fill='black', font=font)
            y += 50
        
        img_path = tmp_path / "email_test.png"
        img.save(str(img_path))
        return str(img_path)
    
    def test_extract_text_ocr_basic(self, sample_text_image):
        """extract_text_ocr should extract text from a simple PNG image"""
        from gateway.screen_memory import extract_text_ocr
        
        result = extract_text_ocr(sample_text_image)
        
        assert isinstance(result, str), "Result should be a string"
        assert len(result) > 0, "Result should not be empty for an image with text"
        print(f"✓ Extracted {len(result)} characters from test image")
        print(f"  Extracted text snippet: {result[:100]}...")
    
    def test_extract_text_ocr_email_accuracy(self, email_focused_image):
        """OCR should accurately extract email addresses (the original bug was email misread)"""
        from gateway.screen_memory import extract_text_ocr
        
        result = extract_text_ocr(email_focused_image)
        
        # Check that we got meaningful text
        assert len(result) > 10, f"Should extract substantial text, got: {result}"
        
        # Check for @ symbol which indicates email detection
        assert '@' in result, f"Should detect email addresses (@ symbol), got: {result}"
        print(f"✓ OCR extracted text with email addresses:")
        print(f"  {result}")
    
    def test_extract_text_ocr_nonexistent_file(self):
        """extract_text_ocr should return empty string for non-existent file"""
        from gateway.screen_memory import extract_text_ocr
        
        result = extract_text_ocr("/nonexistent/path/to/image.png")
        
        assert result == "", f"Should return empty string for non-existent file, got: {result}"
        print("✓ Returns empty string for non-existent file")
    
    def test_extract_text_ocr_corrupted_image(self, tmp_path):
        """extract_text_ocr should return empty string for corrupted/invalid image"""
        from gateway.screen_memory import extract_text_ocr
        
        # Create a file with invalid image data
        corrupted_path = tmp_path / "corrupted.png"
        with open(corrupted_path, 'wb') as f:
            f.write(b"not a valid image data")
        
        result = extract_text_ocr(str(corrupted_path))
        
        assert result == "", f"Should return empty string for corrupted image, got: {result}"
        print("✓ Returns empty string for corrupted image")
    
    def test_extract_text_ocr_empty_image(self, tmp_path):
        """extract_text_ocr should return empty or minimal string for blank image"""
        from gateway.screen_memory import extract_text_ocr
        
        # Create a completely blank white image
        img = Image.new('RGB', (200, 200), color='white')
        img_path = tmp_path / "blank.png"
        img.save(str(img_path))
        
        result = extract_text_ocr(str(img_path))
        
        # Empty image should return empty or very short result (whitespace only)
        assert len(result.strip()) < 5, f"Blank image should return minimal text, got: {result}"
        print(f"✓ Blank image returns minimal text: '{result}'")
    
    def test_extract_text_ocr_uses_2x_upscaling(self):
        """Verify extract_text_ocr implementation uses 2x upscaling"""
        import inspect
        from gateway.screen_memory import extract_text_ocr
        
        source = inspect.getsource(extract_text_ocr)
        
        # Check for 2x upscaling in the code
        assert 'w * 2' in source or '2 * w' in source, "Should upscale width by 2x"
        assert 'h * 2' in source or '2 * h' in source, "Should upscale height by 2x"
        assert 'LANCZOS' in source, "Should use LANCZOS resampling for quality"
        print("✓ extract_text_ocr uses 2x upscaling with LANCZOS")
    
    def test_extract_text_ocr_grayscale_conversion(self):
        """Verify extract_text_ocr converts to grayscale"""
        import inspect
        from gateway.screen_memory import extract_text_ocr
        
        source = inspect.getsource(extract_text_ocr)
        
        # Check for grayscale conversion
        assert '.convert("L")' in source or "convert('L')" in source, "Should convert to grayscale"
        print("✓ extract_text_ocr converts image to grayscale")
    
    def test_extract_text_ocr_tesseract_config(self):
        """Verify extract_text_ocr uses correct Tesseract config (--psm 6 --oem 3)"""
        import inspect
        from gateway.screen_memory import extract_text_ocr
        
        source = inspect.getsource(extract_text_ocr)
        
        assert '--psm 6' in source, "Should use --psm 6 (assume uniform block of text)"
        assert '--oem 3' in source, "Should use --oem 3 (default OCR engine mode)"
        print("✓ extract_text_ocr uses --psm 6 --oem 3 config")


class TestAnalyzeImageOCRIntegration:
    """Test _analyze_image() includes OCR text in prompt"""
    
    def test_analyze_image_calls_ocr(self):
        """_analyze_image should call extract_text_ocr and include result in prompt"""
        import inspect
        from gateway.screen_memory import _analyze_image
        
        source = inspect.getsource(_analyze_image)
        
        # Check that OCR is called
        assert 'extract_text_ocr' in source, "_analyze_image should call extract_text_ocr"
        assert 'ocr_text' in source, "_analyze_image should store OCR result in ocr_text variable"
        print("✓ _analyze_image calls extract_text_ocr")
    
    def test_analyze_image_includes_ocr_in_prompt(self):
        """_analyze_image should include OCR text in the LLM prompt"""
        import inspect
        from gateway.screen_memory import _analyze_image
        
        source = inspect.getsource(_analyze_image)
        
        # Check prompt construction with OCR text
        assert 'OCR-Extracted Text' in source or 'ocr_text' in source
        assert 'ground truth' in source.lower() or 'pixel-perfect' in source.lower(), \
            "Prompt should indicate OCR text is ground truth for names/emails"
        print("✓ _analyze_image includes OCR text in prompt with ground truth indication")
    
    def test_analyze_image_uses_asyncio_to_thread(self):
        """_analyze_image should run OCR in thread to avoid blocking"""
        import inspect
        from gateway.screen_memory import _analyze_image
        
        source = inspect.getsource(_analyze_image)
        
        assert 'asyncio.to_thread' in source, "_analyze_image should use asyncio.to_thread for OCR"
        print("✓ _analyze_image uses asyncio.to_thread for non-blocking OCR")


class TestAnalyzeAndStoreScreenOCRIntegration:
    """Test analyze_and_store_screen() includes OCR text in stored memory"""
    
    def test_analyze_and_store_screen_extracts_ocr(self):
        """analyze_and_store_screen should extract OCR text"""
        import inspect
        from gateway.screen_memory import analyze_and_store_screen
        
        source = inspect.getsource(analyze_and_store_screen)
        
        assert 'extract_text_ocr' in source, "Should call extract_text_ocr"
        assert 'ocr_text' in source, "Should store OCR result"
        print("✓ analyze_and_store_screen extracts OCR text")
    
    def test_analyze_and_store_screen_appends_ocr_to_content(self):
        """analyze_and_store_screen should append OCR text to memory content"""
        import inspect
        from gateway.screen_memory import analyze_and_store_screen
        
        source = inspect.getsource(analyze_and_store_screen)
        
        # Check that OCR is appended to content
        assert 'OCR-extracted text' in source or 'ocr_text' in source
        assert 'verbatim' in source.lower() or 'content +=' in source, \
            "OCR text should be appended to content for searchability"
        print("✓ analyze_and_store_screen appends OCR text to stored memory content")
    
    def test_analyze_and_store_screen_uses_asyncio_to_thread(self):
        """analyze_and_store_screen should run OCR in thread"""
        import inspect
        from gateway.screen_memory import analyze_and_store_screen
        
        source = inspect.getsource(analyze_and_store_screen)
        
        assert 'asyncio.to_thread' in source, "Should use asyncio.to_thread for OCR"
        print("✓ analyze_and_store_screen uses asyncio.to_thread")


class TestAgentOCRIntegration:
    """Test agent.py run_turn() extracts and uses OCR text for image attachments"""
    
    def test_agent_imports_extract_text_ocr(self):
        """agent.py run_turn should import extract_text_ocr for image attachments"""
        import inspect
        from gateway.agent import AgentRunner
        
        source = inspect.getsource(AgentRunner.run_turn)
        
        # Check for OCR import and usage
        assert 'extract_text_ocr' in source, "run_turn should import/use extract_text_ocr"
        print("✓ agent.py run_turn imports extract_text_ocr")
    
    def test_agent_extracts_ocr_for_attachments(self):
        """agent.py should extract OCR text when processing image attachments"""
        import inspect
        from gateway.agent import AgentRunner
        
        source = inspect.getsource(AgentRunner.run_turn)
        
        # Check for OCR extraction with attachments
        assert '_ocr_texts' in source or 'ocr_text' in source, \
            "Should have OCR text collection for attachments"
        assert 'image_attachments' in source or 'attachments' in source
        print("✓ agent.py extracts OCR text for image attachments")
    
    def test_agent_prepends_ocr_to_user_message(self):
        """agent.py should prepend OCR text to user message for LLM context"""
        import inspect
        from gateway.agent import AgentRunner
        
        source = inspect.getsource(AgentRunner.run_turn)
        
        # Check that OCR text is added to the message
        assert 'OCR-Extracted Text' in source or 'ocr_block' in source, \
            "Should prepend OCR text to user message"
        assert 'ground truth' in source.lower() or 'pixel-perfect' in source.lower(), \
            "Should indicate OCR is ground truth for names/emails"
        print("✓ agent.py prepends OCR text to user message with ground truth indication")
    
    def test_agent_handles_both_providers(self):
        """agent.py should handle OCR text for both OpenAI and Anthropic providers"""
        import inspect
        from gateway.agent import AgentRunner
        
        source = inspect.getsource(AgentRunner.run_turn)
        
        # Check provider-specific handling
        assert "provider == \"openai\"" in source or "provider == 'openai'" in source
        assert "provider == \"anthropic\"" in source or "provider == 'anthropic'" in source
        print("✓ agent.py handles OCR for both OpenAI and Anthropic providers")
    
    def test_agent_uses_asyncio_to_thread_for_ocr(self):
        """agent.py should run OCR in thread to avoid blocking event loop"""
        import inspect
        from gateway.agent import AgentRunner
        
        source = inspect.getsource(AgentRunner.run_turn)
        
        assert 'asyncio.to_thread' in source, "Should use asyncio.to_thread for OCR"
        print("✓ agent.py uses asyncio.to_thread for non-blocking OCR")


class TestDockerfileAndRequirements:
    """Test Dockerfile and requirements.txt have correct OCR dependencies"""
    
    def test_dockerfile_has_tesseract(self):
        """Dockerfile should install tesseract-ocr and tesseract-ocr-eng"""
        with open('/app/Dockerfile', 'r') as f:
            dockerfile = f.read()
        
        assert 'tesseract-ocr' in dockerfile, "Dockerfile should install tesseract-ocr"
        assert 'tesseract-ocr-eng' in dockerfile, "Dockerfile should install tesseract-ocr-eng (English language pack)"
        print("✓ Dockerfile includes tesseract-ocr and tesseract-ocr-eng")
    
    def test_requirements_has_pytesseract(self):
        """requirements.txt should have pytesseract"""
        with open('/app/backend/requirements.txt', 'r') as f:
            requirements = f.read()
        
        assert 'pytesseract' in requirements, "requirements.txt should have pytesseract"
        print("✓ requirements.txt includes pytesseract")
    
    def test_requirements_has_pillow(self):
        """requirements.txt should have Pillow (for image preprocessing)"""
        with open('/app/backend/requirements.txt', 'r') as f:
            requirements = f.read()
        
        assert 'pillow' in requirements.lower(), "requirements.txt should have Pillow"
        print("✓ requirements.txt includes Pillow")


class TestOCREndToEnd:
    """End-to-end OCR accuracy tests with realistic screen capture-like images"""
    
    @pytest.fixture
    def screen_capture_like_image(self, tmp_path):
        """Create an image that resembles a screen capture with various text elements"""
        # Create a screen-like image with white background
        img = Image.new('RGB', (1200, 600), color='white')
        draw = ImageDraw.Draw(img)
        
        try:
            header_font = ImageFont.truetype(FONT_PATH, 24)
            body_font = ImageFont.truetype(FONT_PATH, 18)
        except:
            header_font = ImageFont.load_default()
            body_font = ImageFont.load_default()
        
        # Simulate an email client or contact list
        draw.text((50, 30), "Contact List - Mattoni Corporation", fill='black', font=header_font)
        draw.line((50, 60, 1150, 60), fill='gray', width=2)
        
        # Add entries similar to the bug report scenario
        contacts = [
            ("Name: Maria Mikova", "Email: ext_mikova@mattoni.cz", "ID: EMP-2024-001"),
            ("Name: Jan Novak", "Email: jan.novak@mattoni.cz", "ID: EMP-2024-002"),
            ("Name: Peter Koval", "Email: ext_pkoval@mattoni.cz", "ID: EMP-2024-003"),
        ]
        
        y = 80
        for name, email, emp_id in contacts:
            draw.text((50, y), name, fill='black', font=body_font)
            draw.text((350, y), email, fill='blue', font=body_font)
            draw.text((700, y), emp_id, fill='gray', font=body_font)
            y += 40
        
        img_path = tmp_path / "screen_capture.png"
        img.save(str(img_path))
        return str(img_path)
    
    def test_ocr_screen_capture_accuracy(self, screen_capture_like_image):
        """OCR should accurately extract text from screen capture-like image"""
        from gateway.screen_memory import extract_text_ocr
        
        result = extract_text_ocr(screen_capture_like_image)
        
        # Should extract meaningful text
        assert len(result) > 50, f"Should extract substantial text, got {len(result)} chars"
        
        # Should detect @ symbols (email addresses)
        assert '@' in result, "Should detect email addresses"
        
        # Should contain some key text patterns
        has_mattoni = 'mattoni' in result.lower()
        has_contact = 'contact' in result.lower() or 'name' in result.lower()
        
        assert has_mattoni or has_contact, f"Should extract key text patterns, got: {result[:200]}"
        
        print(f"✓ OCR extracted {len(result)} chars from screen capture-like image:")
        print(f"  {result[:300]}...")


# Run pytest with verbose output
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
