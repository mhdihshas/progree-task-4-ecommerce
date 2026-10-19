const API_BASE = "http://127.0.0.1:8000";

const productGrid = document.getElementById("productGrid");
const productState = document.getElementById("productState");
const productTemplate = document.getElementById("productTemplate");

const apiStatus = document.getElementById("apiStatus");
const userLabel = document.getElementById("userLabel");
const authButton = document.getElementById("authButton");
const logoutButton = document.getElementById("logoutButton");

const overlay = document.getElementById("overlay");
const authPanel = document.getElementById("authPanel");
const cartPanel = document.getElementById("cartPanel");

const loginTab = document.getElementById("loginTab");
const registerTab = document.getElementById("registerTab");
const loginForm = document.getElementById("loginForm");
const registerForm = document.getElementById("registerForm");
const authMessage = document.getElementById("authMessage");

const cartButton = document.getElementById("cartButton");
const cartCount = document.getElementById("cartCount");
const cartItems = document.getElementById("cartItems");
const cartEmpty = document.getElementById("cartEmpty");
const cartTotal = document.getElementById("cartTotal");
const cartMessage = document.getElementById("cartMessage");
const checkoutButton = document.getElementById("checkoutButton");

let products = [];
let currentUser = null;
let cart = { items: [], count: 0, total_cents: 0 };

function money(cents) {
  return `$${(cents / 100).toFixed(2)}`;
}

function openPanel(panel) {
  closePanels();
  overlay.classList.remove("hidden");
  panel.classList.remove("hidden");
}

function closePanels() {
  overlay.classList.add("hidden");
  authPanel.classList.add("hidden");
  cartPanel.classList.add("hidden");
}

overlay.addEventListener("click", closePanels);
document.querySelectorAll("[data-close-panel]").forEach((button) => {
  button.addEventListener("click", closePanels);
});

authButton.addEventListener("click", () => openPanel(authPanel));
cartButton.addEventListener("click", async () => {
  if (!currentUser) {
    authMessage.textContent = "Login first to use the persistent cart.";
    openPanel(authPanel);
    return;
  }

  await loadCart();
  openPanel(cartPanel);
});

loginTab.addEventListener("click", () => switchAuth("login"));
registerTab.addEventListener("click", () => switchAuth("register"));

function switchAuth(mode) {
  const loginMode = mode === "login";
  loginTab.classList.toggle("active", loginMode);
  registerTab.classList.toggle("active", !loginMode);
  loginForm.classList.toggle("hidden", !loginMode);
  registerForm.classList.toggle("hidden", loginMode);
  authMessage.textContent = "";
}

async function apiFetch(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    credentials: "include",
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
  });

  let data = null;
  const contentType = response.headers.get("content-type") || "";

  if (contentType.includes("application/json")) {
    data = await response.json();
  }

  if (!response.ok) {
    throw new Error(data?.detail || `Request failed (${response.status})`);
  }

  return data;
}

async function checkApi() {
  try {
    await apiFetch("/");
    apiStatus.textContent = "API Online";
    apiStatus.classList.remove("offline");
    apiStatus.classList.add("online");
  } catch {
    apiStatus.textContent = "API Offline";
    apiStatus.classList.remove("online");
    apiStatus.classList.add("offline");
  }
}

async function loadProducts() {
  productState.classList.remove("hidden");
  productGrid.innerHTML = "";

  try {
    products = await apiFetch("/api/products");
    renderProducts();
    productState.classList.add("hidden");
  } catch (error) {
    productState.textContent = error.message;
  }
}

function renderProducts() {
  productGrid.innerHTML = "";

  products.forEach((product) => {
    const node = productTemplate.content.cloneNode(true);

    node.querySelector(".stock").textContent =
      product.stock > 0 ? `${product.stock} in stock` : "Out of stock";

    node.querySelector(".product-name").textContent = product.name;
    node.querySelector(".product-description").textContent = product.description;
    node.querySelector(".product-price").textContent = money(product.price_cents);

    const button = node.querySelector(".add-btn");
    button.disabled = product.stock <= 0;

    button.addEventListener("click", () => addToCart(product.id));

    productGrid.appendChild(node);
  });
}

async function loadCurrentUser() {
  try {
    currentUser = await apiFetch("/api/auth/me");
  } catch {
    currentUser = null;
  }

  updateAuthUI();

  if (currentUser) {
    await loadCart();
  } else {
    cart = { items: [], count: 0, total_cents: 0 };
    renderCart();
  }
}

function updateAuthUI() {
  if (currentUser) {
    userLabel.textContent = `${currentUser.name} • ${currentUser.email}`;
    authButton.classList.add("hidden");
    logoutButton.classList.remove("hidden");
  } else {
    userLabel.textContent = "Guest";
    authButton.classList.remove("hidden");
    logoutButton.classList.add("hidden");
  }
}

loginForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  authMessage.textContent = "Logging in...";

  try {
    await apiFetch("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({
        email: document.getElementById("loginEmail").value.trim(),
        password: document.getElementById("loginPassword").value,
      }),
    });

    loginForm.reset();
    authMessage.textContent = "Login successful.";
    await loadCurrentUser();
    setTimeout(closePanels, 500);
  } catch (error) {
    authMessage.textContent = error.message;
  }
});

registerForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  authMessage.textContent = "Creating account...";

  try {
    await apiFetch("/api/auth/register", {
      method: "POST",
      body: JSON.stringify({
        name: document.getElementById("registerName").value.trim(),
        email: document.getElementById("registerEmail").value.trim(),
        password: document.getElementById("registerPassword").value,
      }),
    });

    registerForm.reset();
    authMessage.textContent = "Registration successful.";
    await loadCurrentUser();
    setTimeout(closePanels, 500);
  } catch (error) {
    authMessage.textContent = error.message;
  }
});

logoutButton.addEventListener("click", async () => {
  try {
    await apiFetch("/api/auth/logout", { method: "POST" });
  } finally {
    currentUser = null;
    cart = { items: [], count: 0, total_cents: 0 };
    updateAuthUI();
    renderCart();
  }
});

async function addToCart(productId) {
  if (!currentUser) {
    authMessage.textContent = "Login or register before adding products.";
    openPanel(authPanel);
    return;
  }

  try {
    cart = await apiFetch("/api/cart", {
      method: "POST",
      body: JSON.stringify({
        product_id: productId,
        quantity: 1,
      }),
    });

    renderCart();
    cartMessage.textContent = "Product added to your persistent cart.";
    openPanel(cartPanel);
  } catch (error) {
    cartMessage.textContent = error.message;
    openPanel(cartPanel);
  }
}

async function loadCart() {
  if (!currentUser) return;

  try {
    cart = await apiFetch("/api/cart");
    renderCart();
  } catch (error) {
    cartMessage.textContent = error.message;
  }
}

function renderCart() {
  cartItems.innerHTML = "";
  cartCount.textContent = cart.count || 0;
  cartTotal.textContent = money(cart.total_cents || 0);

  const hasItems = cart.items && cart.items.length > 0;
  cartEmpty.classList.toggle("hidden", hasItems);
  checkoutButton.disabled = !hasItems;

  if (!hasItems) return;

  cart.items.forEach((item) => {
    const element = document.createElement("article");
    element.className = "cart-item";

    element.innerHTML = `
      <div class="cart-item-top">
        <div>
          <h3></h3>
          <p></p>
        </div>
        <strong></strong>
      </div>
      <div class="cart-item-controls">
        <label>
          Qty
          <input type="number" min="1" max="${item.stock}" value="${item.quantity}">
        </label>
        <button class="remove-btn" type="button">Remove</button>
      </div>
    `;

    element.querySelector("h3").textContent = item.name;
    element.querySelector("p").textContent =
      `${money(item.price_cents)} each • ${item.stock} available`;
    element.querySelector("strong").textContent = money(item.line_total_cents);

    const qtyInput = element.querySelector("input");
    qtyInput.addEventListener("change", async () => {
      const quantity = Number(qtyInput.value);

      if (!Number.isInteger(quantity) || quantity < 1) return;

      try {
        cart = await apiFetch(`/api/cart/${item.product_id}`, {
          method: "PUT",
          body: JSON.stringify({
            product_id: item.product_id,
            quantity,
          }),
        });

        renderCart();
      } catch (error) {
        cartMessage.textContent = error.message;
        await loadCart();
      }
    });

    element.querySelector(".remove-btn").addEventListener("click", async () => {
      try {
        cart = await apiFetch(`/api/cart/${item.product_id}`, {
          method: "DELETE",
        });
        renderCart();
      } catch (error) {
        cartMessage.textContent = error.message;
      }
    });

    cartItems.appendChild(element);
  });
}

async function startCheckout() {
  cartMessage.textContent = "Creating Stripe checkout...";
  checkoutButton.disabled = true;

  try {
    const data = await apiFetch("/api/checkout/session", {
      method: "POST",
    });

    console.log("Checkout response:", data);

    if (!data || !data.checkout_url) {
      throw new Error("Stripe checkout URL was not returned.");
    }

    cartMessage.innerHTML = `
      Checkout created successfully.<br><br>
      <a
        href="${data.checkout_url}"
        target="_self"
        style="
          display:inline-block;
          padding:12px 18px;
          background:#5ce1b9;
          color:#09271f;
          border-radius:10px;
          font-weight:800;
          text-decoration:none;
        "
      >
        Open Stripe Checkout
      </a>
    `;

  } catch (error) {
    console.error(error);
    cartMessage.textContent = error.message;
  } finally {
    checkoutButton.disabled = false;
  }
}

window.startCheckout = startCheckout;

const checkoutState = new URLSearchParams(window.location.search).get("checkout");
if (checkoutState === "cancelled") {
  cartMessage.textContent = "Checkout was cancelled. Your cart is still saved.";
}

checkApi();
loadProducts();
loadCurrentUser();
