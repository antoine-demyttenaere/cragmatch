import Card from "../../components/Card";
import Icon from "../../components/Icon";
import styles from "./GroupPlaceholder.module.css";

interface GroupPlaceholderProps {
  code: string | null;
}

// Stands in until the group screens move over from the old app.
function GroupPlaceholder({ code }: GroupPlaceholderProps) {
  return (
    <Card as="section">
      <div className={styles.body}>
        <span className={styles.icon}><Icon name="pin" size={32} /></span>
        <h2>Group trips are moving here soon</h2>
        {code && <p className={styles.code}>Group code: <strong>{code}</strong></p>}
        <p className={styles.text}>
          Until then, the old app in <code>frontend/</code> still handles groups, members and group search.
        </p>
      </div>
    </Card>
  );
}

export default GroupPlaceholder;
