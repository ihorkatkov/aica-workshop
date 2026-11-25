// Use LangWatch's standalone (email delivery disabled) account-registration flow.
const [origin, email, password, exists] = process.argv.slice(2);
async function post(path, body) {
  const response = await fetch("http://localhost:5560" + path, {
    method: "POST", headers: { "Content-Type": "application/json", Origin: origin },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new Error(path + " returned " + response.status + ": " + await response.text());
  return response;
}

if (exists === "0") {
  const proof = await post("/api/trpc/auth.requestSignUpVerification", { email });
  const { addressProof } = (await proof.json()).result.data;
  if (!addressProof) throw new Error("Expected the standalone LangWatch email-registration flow.");
  await post("/api/trpc/auth.register", { email, password, addressProof });
}
const login = await post("/api/auth/sign-in/email", { email, password });
if ((await login.json()).user?.email !== email) throw new Error("Workshop sign-in failed.");
