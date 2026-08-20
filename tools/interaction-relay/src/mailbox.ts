import { DurableObject } from "cloudflare:workers";

export class InteractionMailbox extends DurableObject<Env> {}
