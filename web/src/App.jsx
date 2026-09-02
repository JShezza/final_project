import { useState, useEffect, useRef } from "react";
import { health, recommend, searchTracks, sendFeedback } from "./api.js";

const MOODS = ["any", "happy", "sad", "energetic", "calm"];

function App() {
    const [seeds, setSeeds] = useState([]);
    const [query, setQuery] = useState("");
    const [matches, setMatches] = useState([]);
    const [searching, setSearching] = useState(false);

    const [userId, setUserId] = useState("");
    const [novelty, setNovelty] = useState(0.5);
    const [targetMood, setTargetMood] = useState("any");
    const [excludeSeen, setExcludeSeen] = useState(true);
    const [limit, setLimit] = useState(10);

    const [response, setResponse] = useState(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);
    const [ratings, setRatings] = useState({});
    const [blind, setBlind] = useState(false);
    const [status, setStatus] = useState(null);
    const [openTrack, setOpenTrack] = useState(null);

    useEffect(() => {
        health()
            .then(setStatus)
            .catch(() => setError("Can't reach API. Check uvicorn running"));
    }, []);

    // Debounce search
    useEffect(() => {
        if (query.trim().length < 2) {
            setMatches([]);
            return;
        }
        setSearching(true);
        const timer = setTimeout(() => {
            searchTracks(query)
                .then((r) => setMatches(r.results))
                .catch(() => setMatches([]))
                .finally(() => setSearching(false));
        }, 250);
        return () => clearTimeout(timer);
    }, [query]);

    function addSeed(track) {
        if (!seeds.some((s) => s.id === track.id)) setSeeds([...seeds, track]);
        setQuery("");
        setMatches([]);
    }

    // getRecommendations function needed
    async function getRecommendations() {}

    // rate function
    async function rate(trackId, rating) {}
    // HTML Rendering
    return (
        <div className="page">
            <header className="header">
                <h1>NextTrack</h1>
                <p className="tag"> Recommendations from tracks you send!</p>
            </header>
        </div>
    );
}

export default App;
