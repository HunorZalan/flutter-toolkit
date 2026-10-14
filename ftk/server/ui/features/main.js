// Entry point of the optional UI features. ui.js imports this and passes in its API.
// Every feature is loaded on its own, so one broken file cannot take the others down.
const FEATURES = ["selection", "awake", "queue"];

export async function init(api) {
    await Promise.all(FEATURES.map(async (name) => {
        try { (await import(`./${name}.js`)).init(api); }
        catch (err) { console.error(`FTK: feature "${name}" failed to start`, err); }
    }));
}
