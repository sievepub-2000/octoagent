"""Verify OctoAgent WebUI workflow runtime provider management functionality."""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
from dataclasses import asdict, dataclass, field

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


@dataclass
class WorkflowProviderVerificationResult:
    page_loads: bool = False
    provider_badges_visible: bool = False
    creation_ui_accessible: bool = False
    provider_selector_present: bool = False
    langgraph_option_available: bool = False
    openai_agents_option_available: bool = False
    edit_dialog_accessible: bool = False
    edit_provider_selector_present: bool = False
    blockers: list[str] = field(default_factory=list)
    observed_texts: list[str] = field(default_factory=list)


def _note(message: str) -> None:
    print(f"[verify] {message}", file=sys.stderr, flush=True)


def _workflow_creation_button(page):
    patterns = [
        re.compile(r"^(New Workflow|Create Workflow|Add Workflow)$", re.I),
        re.compile(r"^(新建工作流|创建工作流|新增工作流)$"),
    ]
    for pattern in patterns:
        button = page.get_by_role("button", name=pattern)
        if button.count() > 0:
            return button.first
    return None


def _wizard_button(dialog, *names: str):
    for name in names:
        button = dialog.get_by_role("button", name=re.compile(name, re.I))
        if button.count() > 0:
            return button.first
    return None


def verify_runtime_providers() -> WorkflowProviderVerificationResult:
    result = WorkflowProviderVerificationResult()
    target_url = "http://127.0.0.1:19880/workspace/workflows"
    
    with sync_playwright() as playwright:
        _note("launching browser")
        browser_executable = (
            os.environ.get("OCTOPUSAGENT_BROWSER_PATH")
            or playwright.chromium.executable_path
            or shutil.which("chromium-browser")
            or shutil.which("chromium")
            or shutil.which("google-chrome")
        )
        
        try:
            browser = playwright.chromium.launch(
                headless=True,
                executable_path=browser_executable,
            )
            page = browser.new_page()
            
            # Setup error collection
            page_errors: list[str] = []
            console_errors: list[str] = []
            page.on("pageerror", lambda error: page_errors.append(str(error)))
            page.on(
                "console",
                lambda msg: console_errors.append(msg.text)
                if msg.type == "error" and len(console_errors) < 10
                else None,
            )
            
            # Step 1: Navigate to workflow page
            _note(f"opening workflow page: {target_url}")
            try:
                page.goto(target_url, wait_until="networkidle", timeout=30000)
                result.page_loads = True
                _note("✓ Page loads successfully")
            except PlaywrightTimeoutError:
                result.blockers.append("Page failed to load within 30 seconds")
                return result
            except Exception as e:
                result.blockers.append(f"Navigation error: {str(e)}")
                return result
                
            # Collect page title and basic text for observation
            try:
                title = page.title()
                result.observed_texts.append(f"Page title: {title}")
                
                # Get visible text from the page
                body_text = page.locator("body").inner_text(timeout=5000)
                visible_content = " ".join(body_text.split())[:500]  # First 500 chars
                result.observed_texts.append(f"Visible content preview: {visible_content}")
            except Exception as e:
                result.observed_texts.append(f"Could not extract page content: {str(e)}")
            
            # Step 2: Check for auth issues or errors
            try:
                if any(term in page.url for term in ["login", "auth", "signin"]):
                    result.blockers.append("Page redirected to authentication")
                    return result
                    
                if page.locator("text=500").count() > 0 or page.locator("text=error").count() > 0:
                    error_text = page.locator("body").inner_text()[:200]
                    result.blockers.append(f"Server error detected: {error_text}")
                    return result
            except Exception as e:
                result.observed_texts.append(f"Error check failed: {str(e)}")
            
            # Step 3: Check for provider badges/labels on workflow cards
            _note("checking for runtime provider badges on workflow cards")
            try:
                # Look for various provider-related text patterns
                provider_indicators = [
                    "LangGraph", "OpenAI Agents", "Runtime Provider", "Provider", 
                    "runtime:", "provider:", "lang-graph", "openai-agents"
                ]
                
                found_providers = []
                for indicator in provider_indicators:
                    if page.get_by_text(indicator, exact=False).count() > 0:
                        found_providers.append(indicator)
                        
                if found_providers:
                    result.provider_badges_visible = True
                    result.observed_texts.append(f"Found provider indicators: {', '.join(found_providers)}")
                    _note("✓ Provider badges/labels visible")
                else:
                    result.observed_texts.append("No provider badges/labels found on workflow cards")
                    _note("✗ No provider badges visible")
            except Exception as e:
                result.observed_texts.append(f"Badge check error: {str(e)}")
            
            # Step 4: Look for workflow creation UI
            _note("looking for workflow creation UI")
            try:
                creation_button = _workflow_creation_button(page)
                if creation_button is None:
                    result.observed_texts.append("No workflow creation triggers found")
                else:
                    result.observed_texts.append(
                        f"Found creation trigger: {creation_button.inner_text(timeout=2000).strip()}"
                    )
                    creation_button.click(timeout=5000)
                    dialog = page.get_by_role("dialog").last
                    dialog.wait_for(timeout=5000)
                    result.creation_ui_accessible = True
                    _note("✓ Creation UI accessible")

                    textbox = dialog.get_by_role("textbox").first
                    textbox.fill("provider-verification-workflow", timeout=5000)

                    next_button = _wizard_button(dialog, r"^Next$", r"^下一步$")
                    if next_button is None:
                        raise RuntimeError("Wizard next button not found on task step")
                    next_button.click(timeout=5000)

                    dialog = page.get_by_role("dialog").last
                    next_button = _wizard_button(dialog, r"^Next$", r"^下一步$")
                    if next_button is None:
                        raise RuntimeError("Wizard next button not found on agent step")
                    next_button.click(timeout=5000)

                    dialog = page.get_by_role("dialog").last

                    runtime_label = dialog.get_by_text("Runtime provider", exact=False)
                    provider_selector_found = runtime_label.count() > 0
                    selectors = dialog.locator('select, [role="combobox"], [role="listbox"]')
                    if selectors.count() > 0:
                        provider_selector_found = True

                    result.provider_selector_present = provider_selector_found
                    if provider_selector_found:
                        _note("✓ Provider selector present in creation UI")
                    else:
                        _note("✗ No provider selector found in creation UI")

                    provider_combobox = dialog.get_by_role("combobox").last
                    provider_combobox.click(timeout=5000)

                    langgraph_option = page.get_by_role("option", name=re.compile(r"LangGraph", re.I))
                    openai_option = page.get_by_role("option", name=re.compile(r"OpenAI Agents", re.I))
                    result.langgraph_option_available = langgraph_option.count() > 0
                    result.openai_agents_option_available = openai_option.count() > 0

                    if result.langgraph_option_available:
                        result.observed_texts.append("LangGraph option found")
                        _note("✓ LangGraph option available")
                    if result.openai_agents_option_available:
                        result.observed_texts.append("OpenAI Agents option found")
                        _note("✓ OpenAI Agents option available")

                    cancel_button = _wizard_button(dialog, r"^Cancel$", r"^取消$")
                    if cancel_button is not None:
                        cancel_button.click(timeout=5000)
                        page.goto(target_url, wait_until="networkidle", timeout=30000)
            except Exception as e:
                result.observed_texts.append(f"Creation UI check error: {str(e)}")
            
            # Step 6: Check for existing workflow detail/edit functionality
            _note("checking for existing workflow detail/edit dialogs")
            try:
                edit_page = browser.new_page()
                try:
                    edit_page.goto(target_url, wait_until="networkidle", timeout=30000)
                    workflow_cards = edit_page.locator('[data-testid*="workflow"], .workflow-card, [class*="workflow"]')
                    workflow_list_items = edit_page.locator('li:has-text("workflow"), li:has-text("Workflow")')

                    total_workflows = workflow_cards.count() + workflow_list_items.count()
                    result.observed_texts.append(f"Found {total_workflows} potential workflow elements")

                    if total_workflows > 0:
                        try:
                            card_candidates = edit_page.locator("div.group.flex.min-w-0.cursor-pointer")
                            if card_candidates.count() > 0:
                                card_candidates.first.click(timeout=5000)
                            elif workflow_cards.count() > 0:
                                workflow_cards.first.click(timeout=5000)
                            else:
                                workflow_list_items.first.click(timeout=5000)

                            edit_page.wait_for_timeout(2000)

                            edit_provider_indicators = [
                                "Runtime Provider", "Provider", "Edit Provider", "Change Provider"
                            ]

                            for indicator in edit_provider_indicators:
                                if edit_page.get_by_text(indicator, exact=False).count() > 0:
                                    result.edit_provider_selector_present = True
                                    result.observed_texts.append(f"Found edit provider selector: {indicator}")

                            result.edit_dialog_accessible = True
                            if result.edit_provider_selector_present:
                                _note("✓ Edit dialog accessible with provider selector")
                            else:
                                _note("✓ Edit dialog accessible, no provider selector found")

                        except Exception as click_error:
                            result.observed_texts.append(f"Could not access workflow details: {str(click_error)}")
                finally:
                    edit_page.close()
            except Exception as e:
                result.observed_texts.append(f"Edit dialog check error: {str(e)}")
            
            # Collect any error information
            if page_errors:
                result.blockers.extend([f"Page error: {error}" for error in page_errors[:3]])
            if console_errors:
                result.observed_texts.extend([f"Console error: {error}" for error in console_errors[:3]])
            
            browser.close()
            
        except Exception as e:
            result.blockers.append(f"Browser launch error: {str(e)}")
            
    return result


def main() -> None:
    _note("Starting OctoAgent workflow runtime provider verification")
    result = verify_runtime_providers()
    
    # Print results
    print("\n" + "="*60)
    print("OCTOAGENT WORKFLOW PROVIDER VERIFICATION REPORT")
    print("="*60)
    
    print(f"1. Page loads: {'✓ PASS' if result.page_loads else '✗ FAIL'}")
    print(f"2. Provider badges visible: {'✓ PASS' if result.provider_badges_visible else '✗ FAIL'}")
    print(f"3. Creation UI accessible: {'✓ PASS' if result.creation_ui_accessible else '✗ FAIL'}")
    print(f"4. Provider selector present: {'✓ PASS' if result.provider_selector_present else '✗ FAIL'}")
    print(f"5. LangGraph option available: {'✓ PASS' if result.langgraph_option_available else '✗ FAIL'}")
    print(f"6. OpenAI Agents option available: {'✓ PASS' if result.openai_agents_option_available else '✗ FAIL'}")
    print(f"7. Edit dialog accessible: {'✓ PASS' if result.edit_dialog_accessible else '✗ FAIL'}")
    print(f"8. Edit provider selector present: {'✓ PASS' if result.edit_provider_selector_present else '✗ FAIL'}")
    
    if result.blockers:
        print("\n❌ BLOCKERS:")
        for blocker in result.blockers:
            print(f"   - {blocker}")
    
    if result.observed_texts:
        print("\n📋 OBSERVED TEXT:")
        for text in result.observed_texts:
            print(f"   - {text}")
    
    print("\n" + "="*60)
    
    # Also output JSON for programmatic processing
    print("\nJSON Result:")
    print(json.dumps(asdict(result), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()