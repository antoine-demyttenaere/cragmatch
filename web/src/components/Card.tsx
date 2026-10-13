import type { ReactNode } from "react";

import styles from "./Card.module.css";

interface CardProps {
  as?: "div" | "li" | "section";
  children: ReactNode;
}

function Card({ as: Tag = "div", children }: CardProps) {
  return <Tag className={styles.card}>{children}</Tag>;
}

export default Card;
