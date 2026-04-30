import { promises as fs } from "node:fs";
import path from "node:path";

export async function GET() {
  const templatePath = path.resolve(process.cwd(), "..", "docs", "oneclick_queue_template.xlsx");

  try {
    const file = await fs.readFile(templatePath);
    return new Response(file, {
      headers: {
        "Content-Type":
          "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "Content-Disposition": 'attachment; filename="oneclick_queue_template.xlsx"',
        "Cache-Control": "no-store",
      },
    });
  } catch {
    return Response.json(
      { detail: "queue template not found" },
      { status: 404 },
    );
  }
}
