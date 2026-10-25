import { NextResponse } from "next/server";
import { getDb } from "@/lib/mongodb";

export const revalidate = 60;

export async function GET() {
  try {
    const db = await getDb();
    const brandsCol = db.collection("brands");
    const runsCol = db.collection("runs");

    const total = await brandsCol.countDocuments({});
    const byNiche = await brandsCol
      .aggregate([{ $group: { _id: "$niche", count: { $sum: 1 }, avgScore: { $avg: "$score" } } }, { $sort: { count: -1 } }])
      .toArray();

    const latestRun = await runsCol.find({}).sort({ created_at: -1 }).limit(1).toArray();
    const run = latestRun[0] || null;

    // quota from latest run
    const nicheMap: Record<string, number> = {};
    for (const n of byNiche) nicheMap[n._id || "unknown"] = n.count;

    return NextResponse.json({
      total_brands: total,
      brands_per_niche: nicheMap,
      niche_stats: byNiche,
      latest_run: run,
      generated_at: run?.generated_at || null,
    });
  } catch (e) {
    return NextResponse.json({ error: String(e) }, { status: 500 });
  }
}