// Stakd: Face ID lock (WebAuthn passkey on this device). The data is still protected by the account sign-in;
// this keeps the app closed until Face ID (or the device passcode) says it's you.
(function(){
  var KEY = "stakd-faceid", ASKED = "stakd-faceid-asked";
  var $ = function(id){ return document.getElementById(id); };
  var root = document.documentElement;
  var supported = !!(window.PublicKeyCredential && navigator.credentials && navigator.credentials.create);
  var cred = null; try { cred = JSON.parse(localStorage.getItem(KEY) || "null"); } catch(e) {}
  var b64 = function(buf){ var s = ""; new Uint8Array(buf).forEach(function(b){ s += String.fromCharCode(b); }); return btoa(s).replace(/\+/g,"-").replace(/\//g,"_").replace(/=+$/,""); };
  var unb64 = function(s){ s = s.replace(/-/g,"+").replace(/_/g,"/"); while (s.length % 4) s += "="; return Uint8Array.from(atob(s), function(c){ return c.charCodeAt(0); }); };
  var rnd = function(n){ return crypto.getRandomValues(new Uint8Array(n)); };
  var lock = $("sfLock"), msg = $("sfMsg"), offer = $("sfOffer"), tog = $("sfToggle");
  var signedIn = false, busy = false, hiddenAt = 0;

  function setLocked(on){ lock.hidden = !on; root.classList.toggle("sf-locked", on); }
  function paintToggle(){ if (!tog) return; tog.hidden = !supported; tog.textContent = cred ? "Face ID lock: On" : "Face ID lock: Off"; tog.setAttribute("aria-pressed", cred ? "true" : "false"); }
  async function unlock(auto){
    if (busy || !cred) return; busy = true; msg.textContent = "";
    try {
      await navigator.credentials.get({ publicKey: { challenge: rnd(32), allowCredentials: [{ type: "public-key", id: unb64(cred.id), transports: ["internal", "hybrid"] }], userVerification: "required", timeout: 60000 } });
      setLocked(false);
    } catch (e) { if (!auto) msg.textContent = "That didn’t work. Tap to try again."; }
    busy = false;
  }
  async function enable(){
    try {
      var c = await navigator.credentials.create({ publicKey: { challenge: rnd(32), rp: { name: "Stakd" },
        user: { id: rnd(16), name: "Stakd", displayName: "Stakd" },
        pubKeyCredParams: [{ type: "public-key", alg: -7 }, { type: "public-key", alg: -257 }],
        authenticatorSelection: { authenticatorAttachment: "platform", userVerification: "required", residentKey: "preferred" }, timeout: 60000 } });
      cred = { id: b64(c.rawId), at: Date.now() }; localStorage.setItem(KEY, JSON.stringify(cred));
      if (window.mpToast) try { mpToast("Face ID is on"); } catch(e) {}
      return true;
    } catch (e) { console.warn("Face ID setup", e); return false; }
    finally { paintToggle(); }
  }
  function disable(){ cred = null; try { localStorage.removeItem(KEY); } catch(e) {} paintToggle(); }

  // the page starts locked if Face ID is on (set in the inline script), until we know who is signed in
  var gate = $("mpGate");
  function onState(){
    var nowIn = !root.classList.contains("mp-locked");
    var gateShown = gate && !gate.hidden;
    if (gateShown) { signedIn = false; setLocked(false); return; }
    if (nowIn && !signedIn) {
      signedIn = true;
      if (cred) { setLocked(true); unlock(true); }
      else if (supported) { var asked = false; try { asked = !!localStorage.getItem(ASKED); } catch(e) {} if (!asked) offer.hidden = false; }
    }
  }
  new MutationObserver(onState).observe(root, { attributes: true, attributeFilter: ["class"] });
  if (gate) new MutationObserver(onState).observe(gate, { attributes: true, attributeFilter: ["hidden"] });
  onState();

  $("sfUnlock").onclick = function(){ unlock(false); };
  $("sfPass").onclick = function(){ disable(); if (window.mpSignOut) mpSignOut(); else location.reload(); };
  $("sfYes").onclick = async function(){ try { localStorage.setItem(ASKED, "1"); } catch(e) {} offer.hidden = true; await enable(); };
  $("sfNo").onclick = function(){ try { localStorage.setItem(ASKED, "1"); } catch(e) {} offer.hidden = true; };
  if (tog) tog.onclick = function(){ if (cred) disable(); else enable(); };
  paintToggle();

  // lock again when the app comes back after 10 minutes in the background
  document.addEventListener("visibilitychange", function(){
    if (document.hidden) { hiddenAt = Date.now(); return; }
    if (cred && signedIn && hiddenAt && Date.now() - hiddenAt > 600000) { setLocked(true); unlock(true); }
  });
})();
