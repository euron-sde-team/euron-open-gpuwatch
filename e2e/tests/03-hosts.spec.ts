import { expect, test } from "@playwright/test";

import { API_URL, asOwner, RUN } from "../helpers";

test("adding a host: a token, the install command, and the host appears when its agent reports", async ({ page, request }) => {
  await asOwner(page, "/hosts");
  await page.getByRole("button", { name: "Add a host" }).first().click();
  await page.locator("#et-name").fill(`e2e nodes ${RUN}`);
  await page.locator("#et-labels").fill(`env=e2e,run=${RUN}`);
  await page.getByRole("button", { name: "Create token" }).click();
  const token = (await page.getByTestId("enrolment-token").textContent())?.trim() ?? "";
  expect(token).toMatch(/^gwe_/);
  await expect(page.getByText("docker run -d --name gpuwatch-agent")).toBeVisible();
  await page.getByRole("button", { name: "Done" }).click();

  // An agent enrols with the token and reports one GPU.
  const enrolled = await request.post(`${API_URL}/ingest/v1/enroll`, {
    data: { token, machine_id: `e2e-machine-${RUN}`, hostname: `e2e-host-${RUN}` },
  });
  expect(enrolled.status()).toBe(201);
  const { host_token } = await enrolled.json();
  const now = new Date().toISOString();
  const gpu = { uuid: `GPU-e2e-${RUN}`, index: 0, name: "NVIDIA A10G", memory_total_mib: 23028 };
  const batch = await request.post(`${API_URL}/ingest/v1/batches`, {
    headers: { authorization: `Bearer ${host_token}` },
    data: {
      batch_id: crypto.randomUUID(),
      agent: { version: "e2e", collector: "nvml", hostname: `e2e-host-${RUN}`, interval_s: 5 },
      gpus: [gpu],
      samples: [{ gpu_uuid: gpu.uuid, ts: now, interval_s: 5, util_gpu: 42, mem_used_mib: 4096, mem_total_mib: 23028, fan_pct: null }],
    },
  });
  expect(batch.status()).toBe(200);

  await page.reload();
  const row = page.locator("li", { hasText: `e2e-host-${RUN}` });
  await expect(row.getByText("Online")).toBeVisible();
  await expect(row.getByText("A10G")).toBeVisible();
  await expect(row.getByText(`run=${RUN}`)).toBeVisible();

  await row.getByRole("button", { name: "Revoke" }).click();
  await page.getByRole("button", { name: "Revoke host" }).click();
  await expect(row.getByText("Revoked")).toBeVisible();
  const refused = await request.post(`${API_URL}/ingest/v1/batches`, {
    headers: { authorization: `Bearer ${host_token}` },
    data: { batch_id: crypto.randomUUID(), agent: { version: "e2e", collector: "nvml", hostname: "x", interval_s: 5 } },
  });
  expect(refused.status()).toBe(401);
});
