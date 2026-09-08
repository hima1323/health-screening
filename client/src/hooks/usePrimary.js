import { useContext } from 'react';
import { PrimaryContext } from '../context/PrimaryContext';

/** The resolved patient and session ids for the signed-in patient. */
export default function usePrimary() {
  return useContext(PrimaryContext);
}
