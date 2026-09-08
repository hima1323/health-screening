import styles from './StatTile.module.css';

/**
 * A small glass tile. Compose it freely, since the label sits above the value in
 * some screens and below it in others:
 *
 *   <StatTile>
 *     <StatTile.Value>72</StatTile.Value>
 *     <StatTile.Label>Pulse</StatTile.Label>
 *   </StatTile>
 */
export default function StatTile({ className = '', children, ...rest }) {
  return (
    <div className={`${styles.tile} ${className}`.trim()} {...rest}>
      {children}
    </div>
  );
}

StatTile.Label = function StatTileLabel({ className = '', children }) {
  return <p className={`${styles.label} ${className}`.trim()}>{children}</p>;
};

StatTile.Value = function StatTileValue({ accent = false, className = '', children }) {
  return <p className={`${accent ? styles.accent : styles.value} ${className}`.trim()}>{children}</p>;
};

StatTile.Unit = function StatTileUnit({ children }) {
  return <span className={styles.unit}>{children}</span>;
};

/** A three-up row of tiles. */
StatTile.Row = function StatTileRow({ className = '', children }) {
  return <div className={`${styles.row} ${className}`.trim()}>{children}</div>;
};
