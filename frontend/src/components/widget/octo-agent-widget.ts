/**
 * OctoAgent Embeddable Widget
 *
 * Lightweight wrapper for embedding OctoAgent chat into external pages
 * via a <script> tag or Web Component (<octo-agent-widget>).
 *
 * Usage as Web Component:
 *   <octo-agent-widget
 *     api-url="http://localhost:19882"
 *     token="your-token"
 *     theme="light"
 *   ></octo-agent-widget>
 *
 * Usage as JS API:
 *   OctoAgentWidget.init({ apiUrl: "...", token: "...", container: "#my-div" });
 */

export interface WidgetConfig {
  apiUrl: string;
  token?: string;
  theme?: "light" | "dark" | "auto";
  position?: "bottom-right" | "bottom-left" | "inline";
  container?: string | HTMLElement;
  width?: string;
  height?: string;
}

const DEFAULT_CONFIG: Partial<WidgetConfig> = {
  theme: "auto",
  position: "bottom-right",
  width: "400px",
  height: "600px",
};

/**
 * Initialise the OctoAgent widget programmatically.
 */
export function initWidget(config: WidgetConfig): void {
  const merged = { ...DEFAULT_CONFIG, ...config };

  const container =
    typeof merged.container === "string"
      ? document.querySelector(merged.container)
      : merged.container;

  if (!container) {
    console.warn("[OctoAgent Widget] No container found — creating floating widget");
    createFloatingWidget(merged);
    return;
  }

  renderInlineWidget(container as HTMLElement, merged);
}

function createFloatingWidget(config: WidgetConfig & typeof DEFAULT_CONFIG): void {
  const wrapper = document.createElement("div");
  wrapper.id = "octo-agent-widget-root";
  wrapper.style.cssText = `
    position: fixed;
    ${config.position === "bottom-left" ? "left: 16px" : "right: 16px"};
    bottom: 16px;
    width: ${config.width};
    height: ${config.height};
    z-index: 9999;
    border-radius: 12px;
    overflow: hidden;
    box-shadow: 0 8px 32px rgba(0,0,0,0.15);
  `;
  document.body.appendChild(wrapper);
  renderInlineWidget(wrapper, config);
}

function renderInlineWidget(
  container: HTMLElement,
  config: WidgetConfig & typeof DEFAULT_CONFIG,
): void {
  const iframe = document.createElement("iframe");
  const params = new URLSearchParams();
  params.set("embed", "true");
  if (config.token) params.set("token", config.token);
  if (config.theme) params.set("theme", config.theme);
  iframe.src = `${config.apiUrl}/widget?${params.toString()}`;
  iframe.style.cssText = "width:100%;height:100%;border:none;";
  iframe.title = "OctoAgent Chat Widget";
  iframe.setAttribute("loading", "lazy");
  container.innerHTML = "";
  container.appendChild(iframe);
}

// Expose global API
if (typeof window !== "undefined") {
  (window as unknown as Record<string, unknown>).OctoAgentWidget = { init: initWidget };
}
