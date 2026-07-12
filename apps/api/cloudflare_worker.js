export default {
  async fetch(request, env) {
    // 1. Only accept POST requests
    if (request.method !== "POST") {
      return new Response("Method not allowed", { status: 405 });
    }

    // 2. Verify the Bearer Token matches your secret
    const authHeader = request.headers.get("Authorization");
    if (authHeader !== `Bearer ${env.WORKER_SECRET}`) {
      return new Response("Unauthorized", { status: 401 });
    }

    try {
      // 3. Extract the prompt from the JSON body
      const { prompt } = await request.json();
      if (!prompt) {
        return new Response("Missing prompt", { status: 400 });
      }

      // 4. Call Cloudflare's Flux-1-Schnell model
      // This is free/included in the Workers Paid plan and very fast.
      const response = await env.AI.run(
        "@cf/black-forest-labs/flux-1-schnell",
        { prompt: prompt }
      );

      // 5. Flux returns a base64 string in response.image.
      const binaryString = atob(response.image);
      const imageBytes = Uint8Array.from(binaryString, (char) => char.codePointAt(0));
      return new Response(imageBytes, {
        headers: {
          "content-type": "image/jpeg",
        },
      });

    } catch (err) {
      return new Response(err.message || "Internal Server Error", { status: 500 });
    }
  }
};
