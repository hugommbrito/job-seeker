import { useLocation } from "react-router";

/** Shows the current URL, so a test can read what the page wrote to it. */
export function LocationProbe() {
  const location = useLocation();
  return <output data-testid="location">{location.pathname + location.search}</output>;
}
