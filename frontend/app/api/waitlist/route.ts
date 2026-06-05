import { NextRequest, NextResponse } from "next/server"

const NOTION_API_URL = "https://api.notion.com/v1/pages"
const NOTION_DATABASE_ID = "376fb2cfb34c80a0bef5d71977d4566c"

export async function POST(req: NextRequest) {
  try {
    const body = await req.json()
    const { firstName, email, challenge, triedBefore, whyNow } = body

    if (!email || !firstName) {
      return NextResponse.json({ error: "First name and email are required" }, { status: 400 })
    }

    // Token set via NOTION_WAITLIST_TOKEN in .env.local
    const notionToken = process.env.NOTION_WAITLIST_TOKEN

    if (!notionToken) {
      // Fallback: log until token is configured
      console.log("[WAITLIST SIGNUP]", { firstName, email, challenge, triedBefore, whyNow })
      return NextResponse.json({ success: true, fallback: true })
    }

    const notionResponse = await fetch(NOTION_API_URL, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${notionToken}`,
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28",
      },
      body: JSON.stringify({
        parent: { database_id: NOTION_DATABASE_ID },
        properties: {
          Name: { title: [{ text: { content: firstName } }] },
          Email: { email: email },
          Challenge: { rich_text: [{ text: { content: challenge || "" } }] },
          "Already Tried": { rich_text: [{ text: { content: triedBefore || "" } }] },
          "Why Now": { rich_text: [{ text: { content: whyNow || "" } }] },
        },
      }),
    })

    if (!notionResponse.ok) {
      const err = await notionResponse.json()
      console.error("[WAITLIST] Notion API error:", err)
      // Return success to user — don't expose Notion errors
      return NextResponse.json({ success: true, notionSync: false })
    }

    return NextResponse.json({ success: true })
  } catch (error) {
    console.error("[WAITLIST] Error:", error)
    return NextResponse.json({ error: "Something went wrong" }, { status: 500 })
  }
}
