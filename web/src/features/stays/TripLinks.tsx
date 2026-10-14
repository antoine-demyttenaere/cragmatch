import type { BookingLinks } from "../../api/types";
import Icon from "../../components/Icon";
import styles from "./TripLinks.module.css";
import { formatDay } from "./tripDates";

interface TripLinksProps {
  checkin: string; // "YYYY-MM-DD"
  checkout: string; // "YYYY-MM-DD"
  guests: number;
  links: BookingLinks;
}

// "4 guests, Sat 17 Oct to Mon 19 Oct" and the two booking searches.
function TripLinks({ checkin, checkout, guests, links }: TripLinksProps) {
  return (
    <div className={styles.booking}>
      <p>
        {guests} {guests === 1 ? "guest" : "guests"}, {formatDay(checkin)} to {formatDay(checkout)}
      </p>
      <div className={styles.bookingLinks}>
        <a href={links.airbnb} target="_blank" rel="noopener noreferrer" className={styles.bookingLink}>
          Search on Airbnb <Icon name="external" size={16} />
        </a>
        <a href={links.booking} target="_blank" rel="noopener noreferrer" className={styles.bookingLink}>
          Search on Booking.com <Icon name="external" size={16} />
        </a>
      </div>
    </div>
  );
}

export default TripLinks;
