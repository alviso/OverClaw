"""
Interactive Browser Tool — powered by the browser-use library.
Runs in a separate subprocess to avoid event loop conflicts with uvicorn.
"""
import os
import sys
import json
import asyncio
import logging
import tempfile
from typing import Optional
from gateway.tools import Tool, register_tool

logger = logging.getLogger("gateway.tools.browser_use")

# Standalone script that runs browser-use in its own process/event loop
_RUNNER_SCRIPT = r'''
import asyncio, os, sys, json, glob, logging

logging.basicConfig(level=logging.INFO, stream=sys.stderr)
log = logging.getLogger("browser_runner")

async def run_browser_task(task, url, max_steps):
    from browser_use import Agent, BrowserSession, Tools, ActionResult
    from browser_use.llm import ChatOpenAI

    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        return {"error": "OPENAI_API_KEY not set"}

    llm = ChatOpenAI(
        model="gpt-4o",
        api_key=api_key,
        temperature=0.0,
        max_completion_tokens=8192,
    )

    chrome_path = "/pw-browsers/chromium-1208/chrome-linux/chrome"
    if not os.path.exists(chrome_path):
        candidates = glob.glob("/pw-browsers/chromium-*/chrome-linux/chrome")
        chrome_path = candidates[0] if candidates else None

    session = BrowserSession(
        headless=True,
        disable_security=True,
        executable_path=chrome_path,
        chromium_sandbox=False,
        args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
        minimum_wait_page_load_time=1.5,
        wait_for_network_idle_page_load_time=3.0,
        wait_between_actions=1.0,
    )

    # --- Custom tools for handling protected input fields ---
    tools = Tools()

    @tools.action(description=(
        "Force-fill a value into a protected or framework-controlled input field "
        "(e.g. Ant Design, Vue, React inputs in modals). Use this when normal typing "
        "into an input field does not work or the value remains empty after typing. "
        "Provide a CSS selector to target the input and the value to set. "
        "Common selectors: 'input[type=password]', '.ant-input', '.ant-modal input', "
        "'input[placeholder*=password]', 'input[placeholder*=Password]'."
    ))
    async def force_fill_input(css_selector: str, value: str, browser_session: BrowserSession) -> ActionResult:
        """Force-fill a value into a protected input field using JavaScript injection."""
        try:
            page = await browser_session.must_get_current_page()
            log.info(f"force_fill_input: selector={css_selector}, value_len={len(value)}")

            # JavaScript that bypasses Vue/React controlled component protections
            js_code = """(selector, val) => {
                // Collect target inputs
                let targets = Array.from(document.querySelectorAll(selector));

                // If none found, look inside modals specifically
                if (!targets.length) {
                    const modals = document.querySelectorAll('.ant-modal, .ant-modal-wrap, [class*=modal], [class*=Modal], .v-modal');
                    modals.forEach(m => {
                        const inp = m.querySelector(selector) || m.querySelector('input[type="password"]') || m.querySelector('input');
                        if (inp && !targets.includes(inp)) targets.push(inp);
                    });
                }

                // Last resort: find any visible password input
                if (!targets.length) {
                    const allInputs = document.querySelectorAll('input[type="password"], input.ant-input');
                    allInputs.forEach(inp => {
                        if (inp.offsetParent !== null) targets.push(inp);
                    });
                }

                if (!targets.length) return 'NOT_FOUND: No element matches ' + selector;

                const results = [];
                for (let i = 0; i < targets.length; i++) {
                    const input = targets[i];
                    try {
                        // Focus the element
                        input.focus();
                        input.click();

                        // Determine the correct prototype for native setter
                        let proto = window.HTMLInputElement.prototype;
                        if (input instanceof HTMLTextAreaElement) {
                            proto = window.HTMLTextAreaElement.prototype;
                        }
                        const descriptor = Object.getOwnPropertyDescriptor(proto, 'value');
                        if (descriptor && descriptor.set) {
                            descriptor.set.call(input, val);
                        } else {
                            input.value = val;
                        }

                        // Dispatch comprehensive events for Vue/React/Angular
                        input.dispatchEvent(new Event('focus', { bubbles: true }));
                        input.dispatchEvent(new Event('compositionstart', { bubbles: true }));
                        input.dispatchEvent(new InputEvent('input', { bubbles: true, data: val, inputType: 'insertText' }));
                        input.dispatchEvent(new Event('compositionend', { bubbles: true }));
                        input.dispatchEvent(new Event('change', { bubbles: true }));
                        input.dispatchEvent(new KeyboardEvent('keydown', { bubbles: true, key: 'a' }));
                        input.dispatchEvent(new KeyboardEvent('keyup', { bubbles: true, key: 'a' }));
                        input.dispatchEvent(new Event('blur', { bubbles: true }));
                        input.focus();

                        // Vue 2 specific trigger
                        try {
                            if (input.__vue__) input.__vue__.$emit('input', val);
                        } catch(e) {}

                        // Vue 3 / Ant Design Vue specific triggers
                        try {
                            const vueKey = Object.keys(input).find(k => k.startsWith('__vnode') || k.startsWith('__vue'));
                            if (vueKey && input[vueKey]) {
                                const node = input[vueKey];
                                const props = node.props || node.memoizedProps || {};
                                if (props.onInput) props.onInput({ target: { value: val } });
                                if (props['onUpdate:value']) props['onUpdate:value'](val);
                                if (props.onChange) props.onChange({ target: { value: val } });
                            }
                        } catch(e) {}

                        results.push('OK input[' + i + '] value_len=' + input.value.length + ' type=' + input.type);
                    } catch(err) {
                        results.push('ERR input[' + i + ']: ' + err.message);
                    }
                }
                return results.join('; ');
            }"""

            result = await page.evaluate(js_code, css_selector, value)
            log.info(f"force_fill_input result: {result}")

            if "NOT_FOUND" in str(result):
                return ActionResult(extracted_content=f"Failed: {result}. Try a different CSS selector.")
            return ActionResult(extracted_content=f"Successfully filled input: {result}")
        except Exception as e:
            log.error(f"force_fill_input error: {e}")
            return ActionResult(extracted_content=f"Error in force_fill_input: {str(e)}")

    @tools.action(description=(
        "LAST RESORT: Click an element using JavaScript. WARNING: These clicks are NOT trusted "
        "by the browser, so they may not trigger Vue/React event handlers. Only use this for "
        "simple HTML buttons like OK/Confirm/Submit inside modals AFTER the modal is already open. "
        "Do NOT use this for main page buttons — use your native click action instead."
    ))
    async def force_click_element(selector_or_text: str, browser_session: BrowserSession) -> ActionResult:
        """Force-click an element using JavaScript dispatch."""
        try:
            page = await browser_session.must_get_current_page()
            log.info(f"force_click_element: {selector_or_text}")

            js_code = """(selectorOrText) => {
                // First try as CSS selector
                let el = null;
                try { el = document.querySelector(selectorOrText); } catch(e) {}

                if (!el) {
                    // Search by text content - find the MOST SPECIFIC (smallest) matching element
                    const candidates = document.querySelectorAll(
                        'button, a, span, div, li, td, p, h1, h2, h3, h4, label, '
                        + '.ant-btn, [role=button], [class*=card], [class*=device], [class*=item], [class*=name]'
                    );
                    const searchText = selectorOrText.toLowerCase().trim();
                    let bestMatch = null;
                    let bestLen = Infinity;

                    for (const c of candidates) {
                        const text = c.textContent.trim().toLowerCase();
                        // Skip elements with very long text (containers)
                        if (text.length > 200) continue;
                        // Check for match
                        if (text === searchText || text.includes(searchText)) {
                            // Prefer exact matches, then shorter text (more specific)
                            const score = text === searchText ? 0 : text.length;
                            if (score < bestLen) {
                                bestLen = score;
                                bestMatch = c;
                            }
                        }
                    }
                    el = bestMatch;
                }

                if (!el) return 'NOT_FOUND: ' + selectorOrText;
                el.scrollIntoView({ behavior: 'smooth', block: 'center' });
                el.focus();
                el.click();
                el.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window }));
                el.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true }));
                el.dispatchEvent(new PointerEvent('pointerup', { bubbles: true }));
                return 'Clicked: <' + el.tagName + '> text=' + el.textContent.trim().substring(0, 80) +
                    ' classes=' + el.className.toString().substring(0, 80);
            }"""

            result = await page.evaluate(js_code, selector_or_text)
            log.info(f"force_click_element result: {result}")

            if "NOT_FOUND" in str(result):
                return ActionResult(extracted_content=f"Failed: {result}")
            return ActionResult(extracted_content=f"Successfully clicked: {result}")
        except Exception as e:
            log.error(f"force_click_element error: {e}")
            return ActionResult(extracted_content=f"Error: {str(e)}")

    @tools.action(description=(
        "Hover over a device card to reveal a hidden overlay button, then click it. "
        "Many UIs hide action buttons behind hover states. This tool handles that by: "
        "1) Finding the card element by device name text, "
        "2) Moving the mouse over it to trigger hover, "
        "3) Waiting for the overlay button to appear, "
        "4) Clicking the button with trusted CDP mouse events. "
        "Use this when you need to click a button that only appears on mouse hover, "
        "like a 'Remote Control' button on a device card."
    ))
    async def hover_and_click_button(
        card_text: str, button_text: str = "Remote Control", browser_session: BrowserSession = None
    ) -> ActionResult:
        """Hover over a card to reveal hidden button, then click it with trusted CDP events."""
        try:
            page = await browser_session.must_get_current_page()
            log.info(f"hover_and_click_button: card={card_text}, button={button_text}")

            # Step 1: Find the card element and get its bounding box
            js_find_card = """(cardText) => {
                const cards = document.querySelectorAll('[class*=device-card], [class*=card]');
                for (const card of cards) {
                    if (card.textContent.toLowerCase().includes(cardText.toLowerCase())) {
                        const rect = card.getBoundingClientRect();
                        if (rect.width > 0 && rect.height > 0) {
                            return JSON.stringify({
                                found: true,
                                x: rect.x + rect.width / 2,
                                y: rect.y + rect.height / 2,
                                width: rect.width,
                                height: rect.height,
                                classes: card.className.toString().substring(0, 100)
                            });
                        }
                    }
                }
                return JSON.stringify({ found: false });
            }"""

            card_raw = await page.evaluate(js_find_card, card_text)
            log.info(f"Card info raw: {card_raw}")

            import json as _json
            card_info = _json.loads(card_raw) if isinstance(card_raw, str) else card_raw

            if not card_info.get('found'):
                return ActionResult(extracted_content=f"Could not find card containing '{card_text}'")

            card_x = float(card_info['x'])
            card_y = float(card_info['y'])

            # Step 2: Use CDP to move mouse over the card (trusted event)
            mouse = await page.mouse
            await mouse.move(card_x, card_y)
            log.info(f"Mouse moved to card center: ({card_x}, {card_y})")

            # Wait for hover state to activate
            await asyncio.sleep(1.5)

            # Step 3: Find the now-visible button
            js_find_button = """(btnText) => {
                const buttons = document.querySelectorAll('button, .ant-btn, [role=button]');
                for (const btn of buttons) {
                    if (btn.textContent.trim().toLowerCase().includes(btnText.toLowerCase())) {
                        const rect = btn.getBoundingClientRect();
                        const style = window.getComputedStyle(btn);
                        const visible = rect.width > 0 && rect.height > 0 &&
                            style.display !== 'none' && style.visibility !== 'hidden' &&
                            parseFloat(style.opacity) > 0;
                        return JSON.stringify({
                            found: visible,
                            x: rect.x + rect.width / 2,
                            y: rect.y + rect.height / 2,
                            text: btn.textContent.trim().substring(0, 50),
                            classes: btn.className.toString().substring(0, 80),
                            visible: visible
                        });
                    }
                }
                // Fallback: find any button in device-card overlay
                const overlays = document.querySelectorAll('[class*=remote-control], [class*=overlay]');
                for (const ov of overlays) {
                    const btn = ov.querySelector('button, .ant-btn');
                    if (btn) {
                        const rect = btn.getBoundingClientRect();
                        return JSON.stringify({
                            found: true,
                            x: rect.x + rect.width / 2,
                            y: rect.y + rect.height / 2,
                            text: btn.textContent.trim().substring(0, 50),
                            classes: btn.className.toString().substring(0, 80),
                            note: 'overlay_fallback'
                        });
                    }
                }
                return JSON.stringify({ found: false });
            }"""

            btn_raw = await page.evaluate(js_find_button, button_text)
            log.info(f"Button info raw: {btn_raw}")
            btn_info = _json.loads(btn_raw) if isinstance(btn_raw, str) else btn_raw

            if not btn_info.get('found'):
                # Try hovering more aggressively
                await mouse.move(card_x - 10, card_y - 10)
                await asyncio.sleep(0.5)
                await mouse.move(card_x, card_y)
                await asyncio.sleep(2)
                btn_raw = await page.evaluate(js_find_button, button_text)
                btn_info = _json.loads(btn_raw) if isinstance(btn_raw, str) else btn_raw

            if not btn_info.get('found'):
                return ActionResult(extracted_content=f"Button '{button_text}' not found after hovering. The overlay may require a different interaction.")

            btn_x = float(btn_info['x'])
            btn_y = float(btn_info['y'])

            # Step 4: Click the button with trusted CDP mouse event
            await mouse.click(btn_x, btn_y)
            log.info(f"Clicked button at ({btn_x}, {btn_y}): {btn_info.get('text')}")

            await asyncio.sleep(2)

            # Step 5: Check if a modal appeared
            js_check_modal = """() => {
                const modals = document.querySelectorAll('.ant-modal, .ant-modal-wrap, [class*=modal]');
                const visible = [];
                modals.forEach((m, i) => {
                    if (m.offsetParent !== null || m.style.display !== 'none') {
                        const inputs = m.querySelectorAll('input');
                        visible.push('Modal[' + i + '] inputs=' + inputs.length + ' class=' + m.className.substring(0, 60));
                    }
                });
                return visible.length ? visible.join('; ') : 'NO_MODALS';
            }"""

            modal_check = await page.evaluate(js_check_modal)
            log.info(f"Modal check after click: {modal_check}")

            result_text = f"Hovered over '{card_text}' card, clicked '{btn_info.get('text')}' at ({btn_x:.0f},{btn_y:.0f}). "
            result_text += f"Modal status: {modal_check}"
            return ActionResult(extracted_content=result_text)

        except Exception as e:
            log.error(f"hover_and_click_button error: {e}")
            return ActionResult(extracted_content=f"Error: {str(e)}")

    @tools.action(description=(
        "Get a snapshot of all visible input fields and buttons on the page, "
        "including those inside modals. Useful for debugging when you cannot "
        "find the right element to interact with."
    ))
    async def inspect_page_inputs(browser_session: BrowserSession) -> ActionResult:
        """Inspect all inputs and buttons on the current page."""
        try:
            page = await browser_session.must_get_current_page()

            js_code = """() => {
                const info = [];
                // Check for modals
                const modals = document.querySelectorAll('.ant-modal, .ant-modal-wrap, [class*=modal], [class*=Modal]');
                info.push('Modals found: ' + modals.length);
                modals.forEach((m, i) => {
                    info.push('Modal[' + i + '] visible=' + (m.style.display !== 'none') + ' classes=' + m.className.substring(0, 100));
                    const inputs = m.querySelectorAll('input, textarea');
                    inputs.forEach((inp, j) => {
                        info.push('  Input[' + j + '] type=' + inp.type + ' placeholder=' + (inp.placeholder || 'none') +
                            ' value_len=' + inp.value.length + ' visible=' + (inp.offsetParent !== null) +
                            ' id=' + inp.id + ' class=' + inp.className.substring(0, 60));
                    });
                    const buttons = m.querySelectorAll('button, .ant-btn');
                    buttons.forEach((btn, j) => {
                        info.push('  Button[' + j + '] text=' + btn.textContent.trim().substring(0, 40) +
                            ' class=' + btn.className.substring(0, 60));
                    });
                });
                // Also check page-level inputs
                const pageInputs = document.querySelectorAll('input[type=password], input[type=text]');
                info.push('Page-level inputs: ' + pageInputs.length);
                pageInputs.forEach((inp, i) => {
                    info.push('  PageInput[' + i + '] type=' + inp.type + ' placeholder=' + (inp.placeholder || 'none') +
                        ' value_len=' + inp.value.length + ' id=' + inp.id);
                });
                return info.join('\\n');
            }"""

            result = await page.evaluate(js_code)
            log.info(f"inspect_page_inputs:\n{result}")
            return ActionResult(extracted_content=result)
        except Exception as e:
            log.error(f"inspect_page_inputs error: {e}")
            return ActionResult(extracted_content=f"Error: {str(e)}")

    @tools.action(description=(
        "Wait for a modal or specific element to appear on the page. "
        "Polls every 500ms for up to the specified seconds. "
        "Use after clicking a button that should open a modal, "
        "to ensure the modal has fully loaded before interacting with it."
    ))
    async def wait_for_element(css_selector: str, timeout_seconds: int = 5, browser_session: BrowserSession = None) -> ActionResult:
        """Wait for an element to appear on the page."""
        try:
            page = await browser_session.must_get_current_page()
            log.info(f"wait_for_element: selector={css_selector}, timeout={timeout_seconds}")

            import time
            start = time.time()
            while time.time() - start < timeout_seconds:
                js_code = """(sel) => {
                    // Try CSS selector first
                    let el = null;
                    try { el = document.querySelector(sel); } catch(e) {}
                    if (el && el.offsetParent !== null) {
                        return 'FOUND: ' + el.tagName + ' class=' + el.className.toString().substring(0, 80);
                    }
                    // Also check for any modals
                    const modals = document.querySelectorAll('.ant-modal, .ant-modal-wrap, [class*=modal]');
                    const visible = [];
                    modals.forEach((m, i) => {
                        if (m.style.display !== 'none' && m.offsetParent !== null) {
                            visible.push('Modal[' + i + '] class=' + m.className.substring(0, 60));
                        }
                    });
                    if (visible.length) return 'MODALS_VISIBLE: ' + visible.join('; ');
                    return 'NOT_FOUND';
                }"""
                result = await page.evaluate(js_code, css_selector)
                if 'FOUND' in result or 'MODALS_VISIBLE' in result:
                    log.info(f"wait_for_element: {result}")
                    return ActionResult(extracted_content=f"Element appeared: {result}")
                await asyncio.sleep(0.5)

            return ActionResult(extracted_content=f"Timeout: element '{css_selector}' did not appear within {timeout_seconds}s")
        except Exception as e:
            log.error(f"wait_for_element error: {e}")
            return ActionResult(extracted_content=f"Error: {str(e)}")

    # --- Build the task ---
    full_task = task
    if url:
        full_task = f"First navigate to {url}. Then: {task}"

    # Add instructions about the custom tools
    full_task += (
        "\n\nCRITICAL INSTRUCTIONS:"
        "\n1. For buttons hidden behind hover overlays (like 'Remote Control' on device cards), "
        "use 'hover_and_click_button' with card_text (device name) and button_text. "
        "This tool handles the hover→reveal→click sequence with trusted mouse events."
        "\n2. After clicking a button that should open a modal, wait and use 'inspect_page_inputs' to check."
        "\n3. If a modal appears with an input field and normal typing does NOT work (value stays empty), "
        "use 'force_fill_input' with a CSS selector to fill it. Common selectors: 'input[type=password]', '.ant-modal input'"
        "\n4. ALWAYS try force_fill_input IMMEDIATELY if your first typing attempt into a modal input fails."
        "\n5. Only use 'force_click_element' as a LAST RESORT for simple OK/Confirm buttons inside an already-open modal."
        "\n6. Use your native click for regular visible buttons and form elements."
    )

    agent = Agent(
        task=full_task,
        llm=llm,
        browser_session=session,
        tools=tools,
        use_vision=True,
        max_actions_per_step=5,
        max_failures=8,
        enable_planning=True,
        step_timeout=120,
    )

    try:
        history = await asyncio.wait_for(
            agent.run(max_steps=max_steps),
            timeout=180,
        )

        parts = []

        if history.is_done():
            final = history.final_result()
            if final:
                parts.append(f"Result: {final}")

        extracted = history.extracted_content()
        if extracted:
            content_str = "\n".join(str(e) for e in extracted if e)
            if content_str.strip():
                parts.append(f"Extracted content:\n{content_str[:3000]}")

        urls = history.urls()
        if urls:
            parts.append(f"URLs visited: {', '.join(urls[:10])}")

        parts.append(f"Steps taken: {history.number_of_steps()}")

        if history.has_errors():
            errors = history.errors()
            if errors:
                err_str = "\n".join(str(e) for e in errors[:3])
                parts.append(f"Errors encountered:\n{err_str[:500]}")

        if not parts:
            parts.append("Task completed but no specific result was extracted.")

        return {"result": "\n\n".join(parts)}

    except asyncio.TimeoutError:
        return {"result": "Browser task timed out after 180 seconds. Try breaking the task into smaller steps."}
    except Exception as e:
        return {"error": str(e)}
    finally:
        try:
            await session.close()
        except Exception:
            pass


if __name__ == "__main__":
    input_data = json.loads(sys.argv[1])
    result = asyncio.run(run_browser_task(
        task=input_data["task"],
        url=input_data.get("url"),
        max_steps=input_data.get("max_steps", 25),
    ))
    print("__BROWSER_RESULT__")
    print(json.dumps(result))
'''


async def _run_browser_subprocess(task: str, url: str = None, max_steps: int = 25) -> str:
    """Run browser-use in a separate subprocess with its own event loop."""

    input_data = json.dumps({"task": task, "url": url, "max_steps": max_steps})

    # Write runner script to a temp file
    script_path = os.path.join(tempfile.gettempdir(), "browser_runner.py")
    with open(script_path, "w") as f:
        f.write(_RUNNER_SCRIPT)

    env = os.environ.copy()

    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable, script_path, input_data,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )

        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=330)
        stdout_str = stdout.decode("utf-8", errors="replace")
        stderr_str = stderr.decode("utf-8", errors="replace")

        # Log stderr for debugging (browser-use logs go there)
        if stderr_str:
            for line in stderr_str.strip().split("\n")[-10:]:
                logger.debug(f"browser subprocess: {line}")

        # Parse result from stdout
        if "__BROWSER_RESULT__" in stdout_str:
            result_json = stdout_str.split("__BROWSER_RESULT__")[-1].strip()
            result = json.loads(result_json)
            if "error" in result:
                return f"Browser agent error: {result['error']}"
            return result.get("result", "Task completed but no result extracted.")
        else:
            # No result marker — something went wrong
            logger.error(f"Browser subprocess output: {stdout_str[-500:]}")
            logger.error(f"Browser subprocess stderr: {stderr_str[-500:]}")
            return f"Browser agent failed to produce a result. Check logs for details."

    except asyncio.TimeoutError:
        try:
            proc.kill()
        except Exception:
            pass
        return "Browser task timed out after 330 seconds."
    except Exception as e:
        logger.exception("Browser subprocess failed")
        return f"Browser agent error: {str(e)}"


# Keep set_browser_session_id as a no-op for backward compatibility
_current_session_id: Optional[str] = None

def set_browser_session_id(session_id: str):
    global _current_session_id
    _current_session_id = session_id


class BrowserUseTool(Tool):
    name = "browser_use"
    description = (
        "Autonomous web browser agent that can perform complex multi-step tasks on websites. "
        "Give it a high-level task description and it will navigate, click, type, scroll, and interact "
        "with web pages to accomplish the goal. "
        "It has special tools for handling protected input fields in modals (Ant Design, Vue, React): "
        "it can force-fill inputs via JavaScript injection when normal typing fails. "
        "Examples: 'Log into example.com with email user@test.com and password secret123', "
        "'Search for Python tutorials on Google and list the top 3 results', "
        "'Navigate to github.com/browser-use and get the star count'. "
        "The agent sees the page visually and makes smart decisions about what to click and type. "
        "It handles SPAs, dynamic content, popups, modals, and multi-tab scenarios automatically."
    )
    parameters = {
        "type": "object",
        "properties": {
            "task": {
                "type": "string",
                "description": (
                    "Natural language description of the browser task to perform. "
                    "Be specific about what you want to achieve, including any credentials or data needed. "
                    "Example: 'Go to https://example.com/login, enter email user@test.com and password mypass, click Sign In, then tell me what's on the dashboard.'"
                ),
            },
            "url": {
                "type": "string",
                "description": "Optional starting URL. If provided, the agent navigates here first before executing the task.",
            },
            "max_steps": {
                "type": "integer",
                "description": "Maximum number of steps the agent can take (default: 25). Increase for complex multi-page tasks.",
            },
        },
        "required": ["task"],
    }

    async def execute(self, params: dict) -> str:
        task = params.get("task", "")
        if not task:
            return "Error: 'task' is required. Describe what you want the browser to do."

        url = params.get("url")
        max_steps = min(params.get("max_steps", 25), 50)

        logger.info(f"Browser agent task: {task[:100]}...")
        result = await _run_browser_subprocess(task, url=url, max_steps=max_steps)
        logger.info(f"Browser agent result: {result[:200]}...")
        return result


register_tool(BrowserUseTool())
